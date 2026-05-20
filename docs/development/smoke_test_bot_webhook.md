# Smoke Test Bot Webhook

Документ описывает smoke-тест webhook-команд MAX bot adapter.

Скрипт проверяет, что bot webhook работает поверх backend MVP API и PostgreSQL через нормализованный тестовый JSON.

## Что Проверяется

- Создание тестовой организации через API.
- Создание тестового чата через API.
- Создание тестовых пользователей через API.
- Добавление пользователей в чат.
- Команда `/задача` через `POST /api/bot/max/webhook`.
- Проверка, что задача создана.
- Команда `/задачи`.
- Команда `/мои_задачи`.
- Команда `/ответ`.
- Команда `/принять`.
- Проверка финального статуса задачи `done`.

## Запуск На VPS

```bash
ssh max-secretary-vps
cd /opt/max_secretary/app
bash scripts/smoke_test_bot_webhook.sh
```

По умолчанию используется:

```bash
BASE_URL=http://localhost
```

Для другого адреса:

```bash
BASE_URL=http://localhost bash scripts/smoke_test_bot_webhook.sh
```

## Формат Webhook Event

Скрипт использует только нормализованный тестовый JSON:

```json
{
  "chat_id": "internal-chat-uuid",
  "user_id": "internal-user-uuid",
  "message_id": "smoke-message-id",
  "text": "/задачи"
}
```

На MVP `chat_id` и `user_id` должны быть внутренними UUID из БД. Поиск или автосоздание по внешним `max_chat_id` и `max_user_id` будет добавлено позже.

## Требования

- `curl`;
- `jq`;
- запущенный production stack;
- примененные Alembic migrations;
- backend с подключенным `/api/bot/max/webhook`.

## Безопасность

Скрипт не использует реальные MAX secrets, токены или приватные ключи.
Реальный MAX Bot API sender не вызывается: `MaxSender` остается stub-адаптером.
