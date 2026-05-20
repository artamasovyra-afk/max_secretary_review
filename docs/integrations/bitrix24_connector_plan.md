# Bitrix24 Connector Plan

Документ фиксирует аудит текущей модели backend и план MVP-коннектора Битрикс24 для блока `0.7.0`.

## Текущее состояние

### Модели интеграции

На момент первичного аудита в backend не было отдельных моделей. Для подготовки коннектора добавлены:

- `IntegrationAccount`;
- `BitrixTaskLink`.

Они расположены в:

```text
backend/app/modules/integrations/models.py
```

Существующий интеграционный слой расположен в:

```text
backend/app/modules/integrations/max/
```

Его можно использовать как пример изоляции внешнего API client, schemas и exceptions.

### Конфигурация

В `backend/app/core/config.py` добавлены базовые настройки:

```text
BITRIX24_ENABLED
BITRIX24_WEBHOOK_URL
BITRIX24_REQUEST_TIMEOUT_SECONDS
BITRIX24_SYNC_ON_TASK_CREATE
BITRIX24_SYNC_ON_STATUS_CHANGE
BITRIX24_SYNC_ON_ACCEPTANCE
BITRIX24_DEFAULT_RESPONSIBLE_ID
BITRIX24_DEFAULT_CREATED_BY_ID
BITRIX24_PROJECT_GROUP_ID
BITRIX24_USE_TASK_CONTROL
```

В `.env.example` значения оставлены безопасными и без реального webhook URL:

```text
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

HTTP client и sync service пока не реализованы.

### DB layout

Отдельной директории `backend/app/db/models/` нет. Модели находятся внутри доменных модулей:

```text
backend/app/modules/tasks/models.py
backend/app/modules/users/models.py
backend/app/modules/chats/models.py
backend/app/modules/organizations/models.py
```

Alembic discovery выполняется через `backend/app/db/base.py`, где импортируются модели модулей.

### Worker

`backend/app/workers/jobs.py` сейчас запускает reminder scheduler:

```text
python -m app.workers.jobs
```

Отдельного worker/job слоя для интеграций или outbox пока нет.

## Текущая доменная модель задач

### Task

`Task` хранит основную карточку:

- `id`
- `organization_id`
- `chat_id`
- `source_message_id`
- `title`
- `description`
- `created_by_user_id`
- `deadline_at`
- `status`
- `priority`
- `completion_rule`
- `external_source`
- `submitted_at`
- `completed_at`
- `cancelled_at`
- `created_at`
- `updated_at`

Важно: `Task` не содержит одного `responsible_user_id`. Несколько исполнителей хранятся отдельно.

### TaskAssignee

`TaskAssignee` хранит исполнителей задачи:

- `task_id`
- `user_id`
- `status`
- `response_required`
- `responded_at`

Есть уникальность пары `task_id + user_id`.

### TaskObserver

`TaskObserver` хранит наблюдателей:

- `task_id`
- `user_id`

Есть уникальность пары `task_id + user_id`.

### TaskResponse

`TaskResponse` хранит ответ исполнителя:

- `task_id`
- `user_id`
- `text`
- `source_message_id`
- `status`

Используется в командах `/ответ` и `/готово`.

### TaskAcceptance

`TaskAcceptance` хранит приемку или отклонение результата постановщиком:

- `task_id`
- `response_id`
- `accepted_by_user_id`
- `decision`
- `comment`

При `accept` задача переводится в `done`, при `reject` возвращается в `in_progress`.

### TaskStatusHistory

`TaskStatusHistory` фиксирует изменения статуса:

- `task_id`
- `old_status`
- `new_status`
- `changed_by_user_id`

Это важная точка для будущей синхронизации статусов во внешние системы.

## MVP-режим: MAX → Битрикс24

Для MVP предлагается односторонняя синхронизация из `max_secretary` в Битрикс24:

```text
MAX chat / WebApp → max_secretary Task → Bitrix24 task
```

Цель MVP:

- создать или обновить задачу в Битрикс24 на основе задачи `max_secretary`;
- сохранить связь между внутренней задачей и внешней задачей Битрикс24;
- не пытаться принимать входящие изменения из Битрикс24 обратно в `max_secretary`.

## Предлагаемые модели

### IntegrationAccount

Нужна для хранения подключения организации к внешней системе.

Поля foundation-модели:

- `id`
- `organization_id`
- `provider` — например `bitrix24`
- `auth_type` — `webhook`, `oauth`, `token` или `none`
- `credentials_encrypted` nullable
- `settings` JSON nullable
- `is_active`
- `created_at`
- `updated_at`

Важно: реальные webhook URL, access tokens и refresh tokens не должны храниться в открытом виде в git или документации. Если credentials будут храниться в БД, они должны попадать только в `credentials_encrypted`.

### BitrixTaskLink

Нужна для связи внутренней задачи и задачи Битрикс24.

Поля foundation-модели:

- `id`
- `organization_id`
- `task_id`
- `bitrix_portal_url` nullable — только безопасный URL портала без токена
- `bitrix_task_id` nullable
- `sync_status` — `pending`, `synced`, `error`, `disabled`
- `last_sync_at` nullable
- `last_error` nullable
- `created_at`
- `updated_at`

Уникальность:

- на одну локальную задачу допускается максимум одна активная связь `BitrixTaskLink`;
- inactive/disabled history можно расширить позже, если понадобится полноценная история sync-связей.

## Какие поля передаем в Битрикс24

MVP mapping из `Task`:

- `title` → название задачи Битрикс24;
- `description` → описание;
- `deadline_at` → крайний срок;
- `priority` → приоритет, если mapping поддержан;
- `created_by_user_id` → постановщик, только если есть mapping пользователя Битрикс24;
- `assignees` → ответственный/соисполнители, только если есть mapping пользователей;
- `observers` → наблюдатели, только если есть mapping пользователей;
- `status` → текстовая отметка или status mapping, если безопасно;
- `id` → внутренний ID `max_secretary` в описании или custom field;
- `chat_id` → ссылка/контекст чата в описании или custom field;
- `source_message_id` → ссылка/контекст исходного сообщения, если доступен.

Практичный MVP без полноценного user mapping:

- создать задачу в Битрикс24 на заранее настроенного ответственного;
- добавить исполнителей и наблюдателей из `max_secretary` текстом в описание;
- добавить внутренний `Task.id` и статус в описание.

## Какие поля пока не синхронизируем

В MVP не синхронизируем:

- реальные файлы и вложения;
- комментарии;
- историю статусов полностью;
- все ответы исполнителей как комментарии Битрикс24;
- приемку/отклонение как отдельный workflow Битрикс24;
- reminder rules;
- WebApp user context;
- удаление исполнителей/наблюдателей;
- изменения из Битрикс24 обратно в `max_secretary`.

Эти данные остаются источником правды внутри `max_secretary`.

## Где лучше вызывать синхронизацию

### 1. Ручной endpoint

Рекомендуемый первый шаг MVP:

```text
POST /api/tasks/{task_id}/integrations/bitrix24/sync
```

Плюсы:

- безопасно для первого релиза;
- легко повторить при ошибке;
- не замедляет создание задачи;
- проще тестировать без реальных webhooks;
- не требует outbox/job инфраструктуры.

### 2. После создания задачи

Можно добавить позже как opt-in:

```text
TaskService.create → enqueue bitrix24 sync
```

Важно не делать внешний HTTP-запрос внутри той же транзакции, где создается задача. Лучше использовать outbox/job или явную post-commit операцию.

### 3. После изменения статуса

Точки:

- `TaskService.update`
- `TaskService.cancel`
- `_apply_completion_rule_after_response`

Подходит для обновления статуса в Битрикс24 после появления `BitrixTaskLink`, но в MVP лучше оставить ручной sync или отдельный retryable job.

### 4. После приемки/отклонения результата

Точки:

- `TaskService.accept_response`
- `TaskService.reject_response`

Для MVP можно синхронизировать итоговый статус:

- `accepted` → задача Битрикс24 закрыта или помечена выполненной;
- `rejected` → задача Битрикс24 возвращена в работу или получает комментарий.

Но это лучше делать после появления надежного status mapping и retry механизма.

## Рекомендуемая архитектура MVP

Создать модуль:

```text
backend/app/modules/integrations/bitrix24/
  client.py
  schemas.py
  exceptions.py
  service.py
  repository.py
```

Разделение ответственности:

- `client.py` — HTTP adapter к Битрикс24 REST API;
- `schemas.py` — request/response DTO;
- `exceptions.py` — понятные ошибки интеграции;
- `repository.py` — `IntegrationAccount`, `BitrixTaskLink`;
- `service.py` — mapping `Task → Bitrix24 payload`, создание/обновление link.

Для запуска синхронизации:

```text
backend/app/api/integrations_bitrix24.py
```

или отдельный router внутри существующего task API.

## Ограничения MVP

- Только направление `max_secretary → Битрикс24`.
- Один активный Bitrix24 account на организацию на первом этапе.
- User mapping может отсутствовать; тогда пользователи передаются текстом.
- Реальные secret values не хранятся в git.
- Нет real-time обратных webhooks из Битрикс24.
- Нет conflict resolution.
- Нет полной синхронизации комментариев и файлов.
- Ошибки синхронизации должны сохраняться в link/status, а не ломать основной task workflow.

## Почему не делаем двустороннюю синхронизацию в MVP

Двусторонняя синхронизация требует:

- устойчивого user mapping между `max_secretary` и Битрикс24;
- mapping статусов и lifecycle rules;
- обработки конфликтов, когда задача меняется одновременно в двух системах;
- идемпотентности входящих webhooks;
- защиты от sync loop;
- очередей/retry/outbox для сетевых ошибок;
- политики, какая система является источником правды.

На текущем этапе `max_secretary` уже является источником правды для задач из MAX-чатов, приемки результата и свода задач. Поэтому MVP должен сначала надежно публиковать задачи в Битрикс24 в одну сторону и сохранять внешний link.

## Безопасность

- Не добавлять реальные webhook URL и токены в `.env.example`, README, docs или тесты.
- Не логировать полный `BITRIX24_WEBHOOK_URL`, access token или refresh token.
- Для production использовать `.env` на VPS или защищенное secret-хранилище.
- Ошибки client должны быть sanitized перед сохранением в `last_error`.

## Открытые TODO

- Уточнить способ авторизации: incoming webhook URL или OAuth app.
- Определить минимальный user mapping для ответственного, соисполнителей и наблюдателей.
- Определить status mapping `max_secretary → Битрикс24`.
- Выбрать первый sync trigger: ручной endpoint или background job.
- Применить и проверить Alembic migration для `IntegrationAccount` и `BitrixTaskLink` на VPS.
- Добавить smoke-тест без реальных секретов через mock/disabled mode.
