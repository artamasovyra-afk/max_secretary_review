# MAX Bot API Integration Plan

Документ фиксирует аудит текущего MAX bot adapter и план перехода от `MaxSender`-заглушки к реальному MAX Bot API client.

## Текущее состояние

Webhook endpoint:

```text
POST /api/bot/max/webhook
```

Файл endpoint:

```text
backend/app/api/bot_max.py
```

Endpoint сохраняет поддержку внутреннего нормализованного тестового формата события:

```json
{
  "chat_id": "string",
  "user_id": "string",
  "message_id": "string",
  "text": "string"
}
```

Поля:

- `chat_id` — на MVP должен содержать внутренний `Chat.id` в формате UUID.
- `user_id` — на MVP должен содержать внутренний `User.id` в формате UUID.
- `message_id` — идентификатор сообщения-источника, сохраняется как `source_message_id` при ответе исполнителя.
- `text` — текст сообщения или команды.

Перед выполнением команд endpoint вызывает `normalize_max_event(raw_event)`, который изолирует mapping внешнего webhook payload в `NormalizedBotEvent`.

Поддерживаемый MAX-like формат на этапе adapter:

```json
{
  "update_type": "message_created",
  "message": {
    "recipient": {
      "chat_id": "string"
    },
    "sender": {
      "user_id": "string"
    },
    "body": {
      "mid": "string",
      "text": "string"
    }
  }
}
```

Неподдержанные события, нетекстовые сообщения и сообщения с пустым `text` возвращаются как `ignored` и не передаются в command workflow.

Ограничение текущего adapter: если `chat_id` или `user_id` приходят как внешние MAX identifiers, сервис возвращает ошибку при выполнении команды. В коде уже оставлены TODO для будущего lookup/autocreate по `max_chat_id` и `max_user_id`.

## Текущие команды

Команды разбираются в:

```text
backend/app/modules/bot/command_parser.py
```

Команды выполняются в:

```text
backend/app/modules/bot/service.py
```

### /задача

Формат:

```text
/задача <текст> | <исполнители> | <срок YYYY-MM-DD> | наблюдатели: <наблюдатели>
```

Назначение: создать задачу в текущем чате.

Текущая логика:

- получает текущий чат по `event.chat_id`;
- получает постановщика по `event.user_id`;
- сопоставляет исполнителей и наблюдателей по `User.display_name`;
- создает задачу через `TaskService.create`;
- готовит task card payload;
- передает outbound в `MaxSender.send_task_card`.

Ограничения:

- сопоставление пользователей по `display_name` временное;
- срок поддерживается как дата `YYYY-MM-DD`;
- описание задачи из команды пока не заполняется.

### /задачи

Формат:

```text
/задачи
```

Назначение: вывести активные задачи текущего чата.

Текущая логика:

- получает чат по `event.chat_id`;
- запрашивает задачи чата через `TaskService.list`;
- исключает `done` и `cancelled`;
- формирует текстовый список;
- передает outbound в `MaxSender.send_message`.

### /мои_задачи

Формат:

```text
/мои_задачи
```

Назначение: вывести задачи текущего пользователя.

Текущая логика:

- получает чат и пользователя;
- строит inbox summary через `TaskService.inbox_summary`;
- берет `summary.my_tasks`;
- формирует текстовый список;
- передает outbound в `MaxSender.send_message`.

### /ответ

Формат:

```text
/ответ <task_id> <текст ответа>
```

Назначение: отправить ответ исполнителя по задаче.

Текущая логика:

- получает пользователя по `event.user_id`;
- проверяет `task_id` как UUID;
- вызывает `TaskService.submit_response`;
- сохраняет `event.message_id` как `source_message_id`;
- передает результат в `MaxSender.send_message`.

### /готово

Формат:

```text
/готово <task_id> <текст ответа>
```

Назначение: отправить финальный ответ исполнителя.

Текущая логика: работает как `/ответ`, создает `TaskResponse` через `TaskService.submit_response`.

### /принять

Формат:

```text
/принять <task_id> <response_id>
```

Назначение: постановщик принимает ответ исполнителя.

Текущая логика:

- получает пользователя по `event.user_id`;
- проверяет `task_id` и `response_id` как UUID;
- вызывает `TaskService.accept_response`;
- передает результат в `MaxSender.send_message`.

### /отклонить

Формат:

```text
/отклонить <task_id> <response_id> <комментарий>
```

Назначение: постановщик отклоняет ответ исполнителя с комментарием.

Текущая логика:

- получает пользователя по `event.user_id`;
- проверяет `task_id` и `response_id` как UUID;
- вызывает `TaskService.reject_response`;
- передает результат в `MaxSender.send_message`.

## Где используется MaxSender

Файл:

```text
backend/app/modules/notifications/max_sender.py
```

Текущие методы:

- `send_message(chat_id, text, user_id=None, reminder_type=None)`
- `send_task_card(chat_id, task)`

### Режим `MAX_SENDER_ENABLED=false`

- не вызывает внешний MAX API;
- логирует outbound-сообщение или карточку задачи;
- возвращает `BotOutboundMessage` с `sent=false`;
- возвращает reason `stub: real MAX API sending is disabled`.

Этот режим используется по умолчанию и безопасен для локальной разработки, тестов и первого production-запуска без реального токена MAX.

### Режим `MAX_SENDER_ENABLED=true`

- `MaxSender` создается через `build_max_sender()`;
- `build_max_sender()` подключает `MaxApiClient` из `backend/app/modules/integrations/max/client.py`;
- `send_message` отправляет текст в чат через MAX Bot API;
- `send_task_card` пока отправляет текстовую карточку задачи;
- ошибки `MaxApiClient` логируются как warning;
- ошибки отправки возвращаются в `BotOutboundMessage(sent=false)` и не валят основной task workflow.

`MAX_BOT_TOKEN` обязателен только для режима `MAX_SENDER_ENABLED=true`. Токен не должен попадать в логи.

Использования:

- `backend/app/api/bot_max.py` — создает sender через `build_max_sender()` для webhook service.
- `backend/app/modules/bot/service.py` — отправляет ответы на команды и ошибки.
- `backend/app/modules/reminders/jobs.py` — отправляет reminder payload через `send_message`.
- Тесты bot/reminder workflows используют `MaxSender` или тестовые sender doubles.

## Конфигурация

Текущие переменные уже есть в `backend/app/core/config.py` и `.env.example`:

```text
MAX_BOT_TOKEN=
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_WEBHOOK_SECRET=
MAX_WEBHOOK_ENABLED=true
MAX_SENDER_ENABLED=false
MAX_REQUEST_TIMEOUT_SECONDS=10
```

Секретными являются `MAX_BOT_TOKEN` и `MAX_WEBHOOK_SECRET`:

- реальные значения не добавлять в git;
- реальные значения хранить только в production `.env` или GitHub Secrets;
- значения не логировать.

## План замены MaxSender на реальный MAX API client

### 1. Добавить отдельный MAX API client

Отдельный HTTP-слой расположен здесь:

```text
backend/app/modules/integrations/max/client.py
```

Ответственность client:

- хранить base URL MAX Bot API;
- добавлять authorization header из `MAX_BOT_TOKEN`;
- выполнять HTTP-запросы;
- обрабатывать timeout, retryable errors и non-2xx responses;
- не знать бизнес-логику задач.

### 2. Оставить MaxSender как adapter

`MaxSender` должен остаться adapter-слоем над client:

- `send_message` превращает внутренний outbound payload в MAX API request;
- `send_task_card` на первом этапе может отправлять текстовую карточку задачи;
- при выключенной интеграции или пустом токене возвращает понятную ошибку или `sent=false` без внешнего вызова.

Так бизнес-логика `MaxBotWebhookService` и reminder jobs не будут зависеть от конкретного формата MAX API.

### 3. Добавить настройки интеграции

Предлагаемые переменные:

```text
MAX_BOT_TOKEN=
MAX_WEBHOOK_SECRET=
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_SENDER_ENABLED=false
MAX_REQUEST_TIMEOUT_SECONDS=10
```

Значения по умолчанию должны быть безопасными:

- если `MAX_SENDER_ENABLED=false`, реальные сообщения не отправляются;
- если `MAX_BOT_TOKEN` пустой, sender не должен делать внешний запрос;
- секретные значения не должны попадать в logs.

### 4. Добавить валидацию webhook

Webhook endpoint проверяет `MAX_WEBHOOK_SECRET`, если secret задан в settings:

- секрет передается в header `X-Max-Webhook-Secret`;
- неверный или отсутствующий header возвращает `401`;
- пустой `MAX_WEBHOOK_SECRET` разрешен для `APP_ENV=local` и `APP_ENV=test`;
- в `APP_ENV=production` пустой `MAX_WEBHOOK_SECRET` логируется как warning при старте приложения;
- само значение secret не логируется.

После уточнения полного формата MAX webhook:

- принять сырой MAX webhook payload в endpoint;
- проверить подпись или secret через `MAX_WEBHOOK_SECRET`, если MAX поддерживает такой механизм;
- нормализовать внешний payload во внутренний `MaxBotWebhookEvent`;
- оставить текущий normalized event как внутренний DTO и тестовый формат.

### 5. Добавить mapping внешних MAX identifiers

Нужно заменить MVP-требование внутренних UUID:

- искать чат по `Chat.max_chat_id`;
- искать пользователя по `User.max_user_id`;
- при необходимости автосоздавать пользователя с минимальными полями;
- при необходимости автосоздавать чат или возвращать понятную ошибку, если организация неизвестна.

Важно: mapping должен быть изолирован в bot integration service/repository, а не размазан по `TaskService`.

### 6. Добавить форматирование сообщений

Подготовить отдельные formatter functions:

- task created;
- task list;
- my tasks;
- response saved;
- accepted/rejected;
- reminder notification.

Это позволит менять внешний вид MAX-сообщений без изменения доменной логики задач.

### 7. Добавить тесты

Минимальные тесты:

- client добавляет auth header, но не логирует token;
- sender не делает внешний запрос при выключенной отправке;
- sender корректно обрабатывает 2xx;
- sender корректно обрабатывает 4xx/5xx;
- webhook normalization из сырого MAX payload;
- backward compatibility для текущего normalized test payload;
- bot command service не меняет бизнес-логику задач.

### 8. Обновить smoke-тесты

Сохранить текущий normalized smoke:

```text
scripts/smoke_test_bot_webhook.sh
```

Добавить отдельный smoke для реального MAX API только после появления безопасного тестового token/contour. Этот smoke не должен запускаться по умолчанию и не должен требовать реальные секреты для обычного CI.

## Что не делаем в первом шаге 0.6.0

- Не меняем бизнес-логику задач.
- Не коммитим реальные токены.
- Не включаем реальную отправку по умолчанию.
- Не смешиваем сырой MAX payload с доменными сервисами задач.
- Не удаляем normalized webhook format, пока он используется smoke-тестами.

## Рекомендуемая последовательность 0.6.0

1. Зафиксировать контракт текущего adapter и тесты совместимости.
2. Добавить `MaxApiClient` с выключенной по умолчанию отправкой.
3. Обновить `MaxSender`, чтобы он мог работать в `stub` и `real` режимах.
4. Добавить webhook normalizer для реального MAX payload.
5. Добавить lookup по `max_user_id` и `max_chat_id`.
6. Подключить реальные outbound-вызовы только после проверки на тестовом контуре.
7. Обновить документацию и smoke-инструкции.
