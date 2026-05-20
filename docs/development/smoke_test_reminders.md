# Smoke Test Reminders

Скрипт `scripts/smoke_test_reminders.sh` проверяет базовый production-like сценарий reminder jobs через API и worker-контейнер.

## Что проверяет

- создание тестовой организации, чата, постановщика и исполнителя;
- создание задачи с `deadline_at` в прошлом;
- запуск `mark_overdue_tasks` внутри Docker Compose worker;
- проверку, что задача перешла в статус `overdue`;
- создание задачи в статусе `waiting_acceptance`;
- запуск `run_due_reminders` внутри worker;
- проверку, что reminder job обработал задачи и передал сообщения в логирующий `MaxSender` stub.

## Запуск

На VPS из корня проекта:

```bash
cd /opt/max_secretary/app
scripts/smoke_test_reminders.sh
```

По умолчанию используются:

```bash
BASE_URL=http://localhost
COMPOSE_FILE=docker-compose.prod.yml
WORKER_SERVICE=worker
PAST_DEADLINE=2000-01-01T00:00:00Z
```

Их можно переопределить:

```bash
BASE_URL=http://localhost \
COMPOSE_FILE=docker-compose.prod.yml \
WORKER_SERVICE=worker \
scripts/smoke_test_reminders.sh
```

## Требования

- запущен production Docker Compose;
- доступны `curl`, `jq`, `docker`;
- backend отвечает на `GET /api/health`;
- worker image содержит backend-код и переменные окружения из `.env`.

## Важно

Скрипт не использует реальные токены MAX и не вызывает реальный MAX API. `run_due_reminders` проходит через `MaxSender`-заглушку, которая логирует `chat_id`, `user_id`, текст сообщения и `reminder_type`.

Dev endpoint для запуска reminders не добавляется: smoke-тест запускает jobs командой внутри worker-контейнера, чтобы не открывать лишний HTTP endpoint в production.
