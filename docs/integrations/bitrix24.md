# Bitrix24

Документ описывает фактическое состояние Bitrix24 Connector MVP в `max_secretary v1.0.0`.

В `v1.0.0` реализованы:

- настройки интеграции через `.env`;
- модели `IntegrationAccount`, `BitrixTaskLink`, `BitrixUserMapping`;
- CRUD API для ручного сопоставления локальных пользователей с `bitrix_user_id`;
- Bitrix24 REST client adapter;
- mapper локальной задачи в payload для `tasks.task.add`;
- manual sync service;
- ручной endpoint синхронизации задачи;
- endpoint статуса синхронизации;
- endpoint retry failed sync;
- WebApp-индикатор статуса синхронизации в Task Details.

Интеграция остается выключенной по умолчанию. Автоматические triggers, two-way sync и импорт из Битрикс24 в `v1.0.0` не реализованы.

## Переменные

```env
BITRIX24_ENABLED=false
BITRIX24_WEBHOOK_URL=
BITRIX24_REQUEST_TIMEOUT_SECONDS=15
BITRIX24_SYNC_ON_TASK_CREATE=false
BITRIX24_SYNC_ON_STATUS_CHANGE=false
BITRIX24_SYNC_ON_ACCEPTANCE=false
BITRIX24_DEFAULT_RESPONSIBLE_ID=
BITRIX24_DEFAULT_CREATED_BY_ID=
BITRIX24_PROJECT_GROUP_ID=
BITRIX24_USE_TASK_CONTROL=true
```

## Режим по умолчанию

`BITRIX24_ENABLED=false` по умолчанию. В этом режиме интеграция не должна выполнять внешние HTTP-запросы в Битрикс24.

Если `BITRIX24_ENABLED=true`, но `BITRIX24_WEBHOOK_URL` пустой, интеграционный слой должен вернуть понятную ошибку конфигурации:

```text
BITRIX24_WEBHOOK_URL is required when BITRIX24_ENABLED=true.
```

## REST client

Bitrix24 REST client находится в `backend/app/modules/integrations/bitrix24/client.py`.

Он поддерживает:

- вызов произвольного REST method через incoming webhook;
- `profile`/ping для проверки доступности;
- базовые методы задач `tasks.task.get`, `tasks.task.add`, `tasks.task.update`;
- timeout;
- retry для безопасных временных ошибок;
- оборачивание HTTP/API ошибок в понятные exceptions.

REST client используется manual sync service при ручной синхронизации задачи. Он не подключен напрямую к основному task workflow, поэтому создание и изменение локальных задач не выполняет автоматические внешние запросы.

Если client создается из application settings, `BITRIX24_ENABLED` должен быть `true`, а `BITRIX24_WEBHOOK_URL` должен быть заполнен. В тестах можно передавать fake webhook URL напрямую в client через mock transport без реальных HTTP-запросов.

## Task mapper

Bitrix24 task mapper находится в `backend/app/modules/integrations/bitrix24/mapper.py`.

Mapper преобразует локальную задачу max_secretary в `fields` для `tasks.task.add`.

Правила MVP:

- `TITLE` берется из `task.title`.
- `DESCRIPTION` формируется текстом и включает описание задачи, local task ID, chat ID, source message ID при наличии, исполнителей, наблюдателей и пометку `Задача создана из max_secretary`.
- `RESPONSIBLE_ID` получает первый исполнитель с active `BitrixUserMapping`.
- Если active mapping исполнителя нет, используется `BITRIX24_DEFAULT_RESPONSIBLE_ID`.
- Если нельзя определить `RESPONSIBLE_ID`, mapper возвращает `Bitrix24MappingError`.
- В Битрикс24 один основной `RESPONSIBLE_ID`; остальные исполнители с active mapping передаются в `ACCOMPLICES`.
- Наблюдатели с active mapping передаются в `AUDITORS`.
- `CREATED_BY` берется из active mapping постановщика.
- Если mapping постановщика нет, используется `BITRIX24_DEFAULT_CREATED_BY_ID`.
- Если mapping постановщика и default `CREATED_BY` отсутствуют, `CREATED_BY` fallback-ом получает `RESPONSIBLE_ID`.
- `DEADLINE` передается в ISO-формате только если у локальной задачи есть deadline.
- `GROUP_ID` добавляется только если заполнен `BITRIX24_PROJECT_GROUP_ID`.

`BITRIX24_USE_TASK_CONTROL` пока не добавляет поле в payload: точное имя поля Bitrix24 REST API должно быть подтверждено перед включением.

## Sync service

Bitrix24 sync service находится в `backend/app/modules/integrations/bitrix24/service.py`.

MVP-режим:

- синхронизация запускается только вручную через API;
- автоматические triggers после создания задачи, смены статуса и приемки результата не включены;
- при `BITRIX24_ENABLED=false` внешние HTTP-запросы не выполняются, а результат помечается как `disabled`;
- ошибки mapping/client/API сохраняются в `BitrixTaskLink.last_error` и переводят связь в `sync_status=error`;
- повторная ручная синхронизация не должна создавать duplicate Bitrix tasks, если у задачи уже есть active `BitrixTaskLink` с `bitrix_task_id`.

Ручные endpoints:

```text
POST /api/integrations/bitrix24/tasks/{task_id}/sync
GET /api/integrations/bitrix24/tasks/{task_id}/status
POST /api/integrations/bitrix24/retry-failed
```

Sync service не является владельцем task workflow: он только читает локальное состояние задачи и фиксирует результат интеграционной операции.

Методы сервиса для update/status/response sync остаются внутренним заделом и не публикуются в MVP router. Они не используются в smoke-test до уточнения контракта и сценариев.

## WebApp-индикаторы

Статус синхронизации с Битрикс24 отображается:

- в Task Details, где доступен полный статус и ручное действие синхронизации.

Статусы:

- `disabled` — интеграция выключена, реальные HTTP-запросы в Битрикс24 не выполняются;
- `pending` — локальная задача еще не синхронизирована и не имеет `BitrixTaskLink`;
- `synced` — локальная задача связана с задачей Битрикс24;
- `error` — при синхронизации была ошибка, детали хранятся в безопасном `last_error`.

Действия WebApp:

- `Синхронизировать с Битрикс24` запускает ручной `POST /api/integrations/bitrix24/tasks/{task_id}/sync`;
- `Повторить синхронизацию` при ошибке в MVP вызывает тот же ручной sync endpoint для конкретной задачи.

Ограничения MVP:

- автоматическая синхронизация не включена;
- двусторонней синхронизации нет;
- статус синхронизации в списке Tasks не отображается;
- внешний URL задачи Битрикс24 может быть добавлен позже;
- реальные webhook URL и credentials не отображаются в WebApp.

## Безопасность

`BITRIX24_WEBHOOK_URL` является секретом, если содержит webhook token или другой credential. Реальное значение нельзя коммитить, добавлять в README, хранить в документации или выводить в логи.

Для production значение задается только в `.env` на VPS или в защищенном secret-хранилище.

## Текущие ограничения

- Двусторонняя синхронизация не реализована.
- Импорт задач и пользователей из Битрикс24 не реализован.
- Удаление задач в Битрикс24 не реализовано.
- Автоматические trigger-флаги пока должны оставаться `false`.
- User mapping создается вручную через API.
