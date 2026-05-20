# MAX Integration

Документ описывает текущее состояние MAX-интеграции в `max_secretary` v1.0.0.

## Текущий статус

В проекте уже есть базовый adapter layer для MAX Bot:

- webhook endpoint: `POST /api/bot/max/webhook`;
- нормализованный внутренний формат bot event;
- слой нормализации MAX-like webhook событий;
- parser команд без доступа к БД;
- service layer, который связывает команды с задачами;
- `MaxSender` adapter с двумя режимами: logging stub и реальная отправка;
- MAX Bot API client adapter на `httpx`;
- проверка webhook secret через header `X-Max-Webhook-Secret`;
- настройки `MAX_SENDER_ENABLED`, `MAX_WEBHOOK_SECRET`, `MAX_WEBHOOK_ENABLED`.

Реальная отправка в MAX по умолчанию выключена. В этом режиме `MaxSender` логирует подготовленное исходящее сообщение и не делает внешние HTTP-запросы.

## Webhook Event

MVP поддерживает тестовый нормализованный JSON:

```json
{
  "chat_id": "CHAT_UUID",
  "user_id": "USER_UUID",
  "message_id": "message-1",
  "text": "/задачи"
}
```

Для команд, которые выполняют бизнес-логику, `chat_id` и `user_id` на v1.0.0 должны быть внутренними UUID из backend. Поиск или автосоздание по внешним `max_chat_id` и `max_user_id` остается будущей задачей.

Также есть функция нормализации MAX-like событий. Неподдерживаемые события и события без текстового сообщения помечаются как ignored.

## Команды

### `/задача`

Формат:

```text
/задача <текст> | <исполнители> | <срок YYYY-MM-DD> | наблюдатели: <наблюдатели>
```

Примеры:

```text
/задача Подготовить отчет | Иван | 2026-05-20
/задача Подготовить отчет | Иван, Мария | 2026-05-20 | наблюдатели: Сергей, Анна
```

Создает задачу в текущем чате. Исполнители и наблюдатели на MVP сопоставляются по `display_name`.

### `/задачи`

Показывает активные задачи текущего чата, кроме задач в статусах `done` и `cancelled`.

### `/мои_задачи`

Показывает задачи текущего пользователя через единый summary задач.

### `/ответ`

Формат:

```text
/ответ <task_id> <текст ответа>
```

Создает `TaskResponse` от исполнителя.

### `/готово`

Формат:

```text
/готово <task_id> <текст ответа>
```

На v1.0.0 работает как финальный ответ исполнителя и использует тот же backend workflow, что `/ответ`.

### `/принять`

Формат:

```text
/принять <task_id> <response_id>
```

Принимает ответ исполнителя. Backend проверяет правила приемки задачи: принять результат может постановщик задачи.

### `/отклонить`

Формат:

```text
/отклонить <task_id> <response_id> <комментарий>
```

Отклоняет ответ исполнителя с комментарием и возвращает задачу в рабочий статус по текущей task workflow логике.

## MAX Sender

`MaxSender` работает в двух режимах.

При `MAX_SENDER_ENABLED=false`:

- реальные запросы в MAX Bot API не выполняются;
- исходящее сообщение или task card пишется в лог;
- это безопасный режим по умолчанию для VPS, smoke-тестов и закрытого контура.

При `MAX_SENDER_ENABLED=true`:

- используется `MaxApiClient`;
- `send_message(chat_id, text)` отправляет сообщение через MAX Bot API;
- `send_task_card(chat_id, task)` пока отправляет текстовое представление карточки задачи;
- ошибки отправки логируются и не должны ломать основной task workflow.

`MAX_BOT_TOKEN` используется только внутри client adapter и не должен логироваться.

## Security

- `MAX_BOT_TOKEN` нельзя коммитить, хранить в README или выводить в логи.
- `MAX_WEBHOOK_SECRET` должен быть задан для production webhook.
- Если `MAX_WEBHOOK_SECRET` задан, endpoint требует header `X-Max-Webhook-Secret`.
- Неверный webhook secret возвращает `401`.
- В `APP_ENV=production` пустой `MAX_WEBHOOK_SECRET` логируется как warning при старте приложения.
- `MAX_WEBHOOK_ENABLED` присутствует в settings и `.env.example` как флаг включения webhook-логики. В v1.0.0 основной runtime guard endpoint — проверка `MAX_WEBHOOK_SECRET`; если на контуре webhook должен быть полностью выключен, дополнительно закрывайте endpoint на уровне reverse proxy/ingress до отдельного hardening изменения.

## Deployment

Переменные задаются в production `.env` на VPS.

| Variable | Safe default | Назначение |
| --- | --- | --- |
| `MAX_BOT_TOKEN` | empty | Token MAX bot. Заполняется только при включении реальной отправки. |
| `MAX_API_BASE_URL` | `https://platform-api.max.ru` | Base URL MAX Bot API. |
| `MAX_WEBHOOK_SECRET` | empty before setup | Secret для проверки входящих webhook-запросов. Для production webhook должен быть задан. |
| `MAX_WEBHOOK_ENABLED` | `true` | Флаг включения webhook-логики в конфигурации. |
| `MAX_SENDER_ENABLED` | `false` | Включает реальные исходящие запросы в MAX Bot API. |
| `MAX_REQUEST_TIMEOUT_SECONDS` | `10` | Timeout исходящих MAX API запросов. |

Безопасное состояние по умолчанию:

- `MAX_SENDER_ENABLED=false`;
- `MAX_BOT_TOKEN` пустой, пока реальная отправка не включена;
- `MAX_WEBHOOK_SECRET` должен быть заполнен перед подключением production webhook;
- внешние MAX-запросы не выполняются, пока явно не включен sender.

После изменения `.env` перезапустите сервисы:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Проверка backend:

```bash
curl http://localhost/api/health
```

Проверка webhook тестовым нормализованным событием:

```bash
curl -X POST http://localhost/api/bot/max/webhook \
  -H "Content-Type: application/json" \
  -H "X-Max-Webhook-Secret: CHANGE_ME" \
  -d '{
    "chat_id": "CHAT_UUID",
    "user_id": "USER_UUID",
    "message_id": "test-message-1",
    "text": "/задачи"
  }'
```

## Ограничения v1.0.0

- Полноценная MAX WebApp auth еще не реализована.
- Некоторые WebApp/API действия используют dev auth context и временные headers.
- Inline buttons и native task cards в MAX не реализованы.
- Создание задачи из reply message пока не реализовано.
- Поиск пользователей для команды `/задача` временно идет по `display_name`.
- Реальная отправка в MAX включается только явной настройкой `MAX_SENDER_ENABLED=true` и заполнением `MAX_BOT_TOKEN`.
- Закрытый контур должен оставлять внешние интеграции выключенными, если MAX API недоступен.
