# Bitrix24 Sync Service Plan

## Цель

Bitrix24 Sync Service должен быть отдельным интеграционным слоем, который не смешивает бизнес-логику задач max_secretary с внешним API Битрикс24.

Основные цели:

- ручная синхронизация локальной задачи в Битрикс24;
- сохранение связи через `BitrixTaskLink`;
- обработка состояний `disabled`, `error`, `synced`;
- повторная попытка синхронизации для failed/error записей;
- защита основного task workflow от падений внешней интеграции.

## Методы будущего сервиса

Планируемый интерфейс:

```python
sync_task_create(task_id)
sync_task_update(task_id)
sync_task_status(task_id)
sync_task_response(task_id, response_id)
retry_failed_sync(limit=50)
```

### sync_task_create(task_id)

Создает задачу в Битрикс24 по локальной задаче max_secretary.

Ожидаемая логика:

- загрузить локальную задачу с исполнителями, наблюдателями и постановщиком;
- проверить, что `BITRIX24_ENABLED=true`;
- проверить существующий `BitrixTaskLink`;
- не создавать дубль, если активная связь уже существует;
- построить payload через `Bitrix24TaskMapper`;
- вызвать `Bitrix24Client.create_task`;
- сохранить `bitrix_task_id`, `sync_status=synced`, `last_sync_at`.

### sync_task_update(task_id)

Обновляет основные поля уже связанной задачи в Битрикс24.

Ожидаемая логика:

- найти существующий active `BitrixTaskLink`;
- если связи нет, вернуть понятную ошибку или предложить `sync_task_create`;
- построить payload обновления;
- вызвать `Bitrix24Client.update_task`;
- обновить `sync_status` и `last_sync_at`.

### sync_task_status(task_id)

Синхронизирует статус локальной задачи с Битрикс24.

Ожидаемая логика:

- найти `BitrixTaskLink`;
- преобразовать локальный `TaskStatus` в допустимое состояние Битрикс24;
- вызвать update через REST client;
- не менять локальный task workflow при ошибке Битрикс24.

### sync_task_response(task_id, response_id)

Синхронизирует ответ исполнителя как комментарий или обновление задачи в Битрикс24.

Ожидаемая логика:

- проверить, что response относится к task;
- найти `BitrixTaskLink`;
- сформировать текст ответа;
- отправить его в Битрикс24 через отдельный client method, когда endpoint будет подтвержден;
- на первом этапе можно оставить TODO до подтверждения REST метода комментариев.

### retry_failed_sync(limit=50)

Повторяет синхронизацию записей, которые ранее завершились ошибкой.

Ожидаемая логика:

- выбрать до `limit` записей `BitrixTaskLink` со статусом `error`;
- пропустить `disabled`;
- повторить безопасный сценарий в зависимости от наличия `bitrix_task_id`;
- обновить `last_error`, `last_sync_at`, `sync_status`.

## Первый MVP

В первом MVP sync service нужно сделать минимальным и управляемым вручную.

Входит:

- ручной endpoint sync;
- disabled mode при `BITRIX24_ENABLED=false`;
- понятное error logging;
- защита от duplicate Bitrix tasks;
- сохранение и обновление `BitrixTaskLink`;
- отсутствие автоматических triggers.

Поведение при `BITRIX24_ENABLED=false`:

- внешние HTTP-запросы не выполняются;
- сервис возвращает понятный disabled-result;
- `BitrixTaskLink` можно не создавать или помечать `sync_status=disabled`, если это нужно для аудита.

## Что пока не делать

В следующем пакете не реализуем:

- автоматическую синхронизацию on task create;
- автоматическую синхронизацию on status change;
- автоматическую синхронизацию on acceptance;
- двустороннюю синхронизацию;
- импорт задач из Битрикс24;
- импорт пользователей из Битрикс24;
- удаление задач в Битрикс24;
- влияние ошибки Битрикс24 на основной task workflow.

## Риски

Основные риски:

- отсутствует `BitrixUserMapping` для исполнителей, наблюдателей или постановщика;
- не задан `BITRIX24_DEFAULT_RESPONSIBLE_ID`;
- Bitrix24 API недоступен;
- `BITRIX24_WEBHOOK_URL` неверный или просроченный;
- возможны дубли задач при повторной ручной синхронизации;
- локальный task workflow не должен падать из-за ошибки Битрикс24;
- webhook URL содержит секрет и не должен попадать в логи, БД в открытом виде или git.

## Границы пакета

Sync service должен использовать уже подготовленные компоненты:

- `Bitrix24Client` для REST API;
- `Bitrix24TaskMapper` для payload `tasks.task.add`;
- `BitrixTaskLink` для связи локальной и внешней задачи;
- `BitrixUserMapping` для сопоставления пользователей.

Task workflow остается владельцем локальной бизнес-логики. Bitrix24 sync service только читает локальное состояние и фиксирует результат синхронизации.

## MVP endpoints

Публичные ручные endpoints первого MVP:

```text
POST /api/integrations/bitrix24/tasks/{task_id}/sync
GET /api/integrations/bitrix24/tasks/{task_id}/status
POST /api/integrations/bitrix24/retry-failed
```

Эти endpoints не подключаются к основному task workflow автоматически. Их можно использовать вручную или из будущего retry/job слоя.

Внутренние методы `sync_task_update`, `sync_task_status` и `sync_task_response` остаются заделом сервиса, но не публикуются в MVP router до уточнения публичного контракта.
