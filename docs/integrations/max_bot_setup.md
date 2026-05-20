# MAX Bot setup

Документ описывает базовую настройку MAX Bot integration для проекта `max_secretary`.

## Переменные

Для интеграции используются переменные:

- `MAX_BOT_TOKEN` — токен MAX бота. Не коммитить, не хранить в README, не выводить в логи.
- `MAX_API_BASE_URL` — base URL MAX Bot API. По умолчанию: `https://platform-api.max.ru`.
- `MAX_WEBHOOK_SECRET` — secret для проверки входящих webhook-запросов.
- `MAX_WEBHOOK_ENABLED` — флаг включения webhook-логики.
- `MAX_SENDER_ENABLED` — флаг реальной отправки сообщений через MAX Bot API.

## Где заполнять на VPS

На VPS значения заполняются в production `.env`:

```bash
cd /opt/max_secretary/app
nano .env
```

Пример без реальных секретов:

```env
MAX_BOT_TOKEN=
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_WEBHOOK_SECRET=
MAX_WEBHOOK_ENABLED=true
MAX_SENDER_ENABLED=false
```

## Проверка backend

```bash
curl http://localhost/api/health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "service": "max_secretary"
}
```

## Проверка webhook тестовым событием

Если `MAX_WEBHOOK_SECRET` пустой в local/test окружении:

```bash
curl -X POST http://localhost/api/bot/max/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": "CHAT_UUID",
    "user_id": "USER_UUID",
    "message_id": "test-message-1",
    "text": "/задачи"
  }'
```

Если `MAX_WEBHOOK_SECRET` задан:

```bash
curl -X POST http://localhost/api/bot/max/webhook \
  -H "Content-Type: application/json" \
  -H "X-Max-Webhook-Secret: CHANGE_ME_WEBHOOK_SECRET" \
  -d '{
    "chat_id": "CHAT_UUID",
    "user_id": "USER_UUID",
    "message_id": "test-message-1",
    "text": "/задачи"
  }'
```

`CHAT_UUID` и `USER_UUID` на MVP должны быть внутренними UUID из backend, если команда должна выполнить бизнес-логику.

## Включить реальную отправку

```env
MAX_SENDER_ENABLED=true
```

При включенной отправке также должен быть заполнен `MAX_BOT_TOKEN`.

После изменения `.env` перезапустите сервисы:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## Отключить реальную отправку

```env
MAX_SENDER_ENABLED=false
```

В этом режиме `MaxSender` только логирует исходящие сообщения и не делает внешние запросы в MAX Bot API.

## Ограничения MVP

- `send_task_card` пока отправляет текстовую карточку задачи.
- Кнопки и inline-actions будут подключены позже.
- User matching пока временный: команды MVP используют внутренние UUID и сопоставление исполнителей по `display_name`.
- Безопасность webhook зависит от корректного и непубличного `MAX_WEBHOOK_SECRET`.
