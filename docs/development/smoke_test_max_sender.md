# Smoke test: MAX sender disabled/mock mode

Документ описывает проверку `MaxSender` в режиме без реальной отправки сообщений в MAX.

## Назначение

Smoke-тест проверяет:

- backend healthcheck;
- webhook endpoint `POST /api/bot/max/webhook`;
- обработку команды `/задачи`;
- что при `MAX_SENDER_ENABLED=false` отправка остается логирующим placeholder и не делает реальных HTTP-запросов в MAX Bot API;
- логи backend/worker, если тест выполняется рядом с Docker Compose.

## Требования

На машине должны быть доступны:

- `curl`;
- `jq`;
- запущенный backend через nginx или напрямую по `BASE_URL`;
- Docker Compose опционально, только для проверки логов.

Реальные MAX токены для этого теста не нужны.

## Запуск

На VPS из директории проекта:

```bash
cd /opt/max_secretary/app
scripts/smoke_test_max_sender.sh
```

Если backend доступен не на `http://localhost`:

```bash
BASE_URL=http://localhost scripts/smoke_test_max_sender.sh
```

Если `MAX_WEBHOOK_SECRET` настроен и endpoint требует header, передайте secret через переменную окружения текущей shell-сессии:

```bash
WEBHOOK_SECRET=CHANGE_ME_WEBHOOK_SECRET scripts/smoke_test_max_sender.sh
```

Не коммитьте secret и не добавляйте его в документацию.

## Что делает скрипт

1. Проверяет:

```bash
curl http://localhost/api/health
```

2. Создает тестовую организацию и чат через backend API.

3. Отправляет тестовое normalized webhook событие:

```json
{
  "chat_id": "CHAT_UUID",
  "user_id": "00000000-0000-0000-0000-000000000000",
  "message_id": "smoke-max-sender",
  "text": "/задачи"
}
```

4. Проверяет, что backend вернул успешный ответ и `outbound.sent=false`.

5. Проверяет, что `outbound.reason` содержит `disabled`.

6. Если доступен Docker Compose, проверяет backend logs на marker:

```text
MAX sender stub message
```

## Ожидаемый результат

В конце скрипт выводит:

```text
MAX sender disabled smoke test passed
sender_sent=false
sender_reason=stub: real MAX API sending is disabled
```

## Ограничения

- Тест не использует реальные `MAX_BOT_TOKEN`.
- Тест не проверяет реальную доставку сообщений в MAX.
- Если `MAX_SENDER_ENABLED=true`, smoke-тест должен упасть на проверке `outbound.sent=false`.
- Проверка логов пропускается, если Docker Compose недоступен в текущем окружении.
