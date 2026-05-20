# Создание .env на VPS

Документ описывает создание `.env` на VPS для production-запуска проекта `max_secretary`.

`.env` не должен храниться в GitHub.

## Создать .env из примера

```bash
cd /opt/max_secretary/app
cp .env.example .env
nano .env
```

## Пример значений

```env
APP_NAME=max_secretary
APP_ENV=production
DEBUG=false
DEV_AUTH_ENABLED=false

POSTGRES_DB=max_secretary
POSTGRES_USER=max_secretary
POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD

DATABASE_URL=<postgresql asyncpg URL for the postgres container>
REDIS_URL=redis://redis:6379/0

MAX_BOT_TOKEN=
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_WEBHOOK_SECRET=
MAX_WEBHOOK_ENABLED=true
MAX_SENDER_ENABLED=false
MAX_REQUEST_TIMEOUT_SECONDS=10

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

AI_ENABLED=false
AI_PROVIDER=none
```

## Production baseline

Для пилотного production-запуска ожидаемые безопасные значения:

- `APP_ENV=production`
- `DEBUG=false`
- `DEV_AUTH_ENABLED=false`, если временный dev auth через headers явно не нужен
- `MAX_SENDER_ENABLED=false`, если реальная отправка в MAX не включена
- `BITRIX24_ENABLED=false`, если реальный Bitrix24 webhook не настроен
- `BITRIX24_WEBHOOK_URL=` пустой, если интеграция выключена
- `AI_ENABLED=false`

`.env` должен существовать только на сервере или в защищенном secret-хранилище и не должен коммититься.

## Обязательные переменные для первого запуска

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `REDIS_URL`

`DATABASE_URL` должен использовать PostgreSQL в формате `postgresql+asyncpg://...`.
SQLite не используется как fallback и не должен указываться в production `.env`.

## MAX Bot API

- `MAX_BOT_TOKEN` — токен бота MAX. Реальное значение не коммитить и не выводить в логи.
- `MAX_API_BASE_URL` — base URL MAX Bot API. По умолчанию используется `https://platform-api.max.ru`.
- `MAX_WEBHOOK_SECRET` — secret для проверки webhook. Если задан, endpoint `POST /api/bot/max/webhook` требует header `X-Max-Webhook-Secret`.
- `MAX_WEBHOOK_ENABLED` — включает прием webhook endpoint.
- `MAX_SENDER_ENABLED` — включает реальную отправку через MAX Bot API.
- `MAX_REQUEST_TIMEOUT_SECONDS` — timeout исходящих MAX API запросов.

Для безопасного первого запуска оставьте:

```env
MAX_SENDER_ENABLED=false
```

В этом режиме используется логирующий режим `MaxSender`, а реальные сообщения в MAX не отправляются.

В `APP_ENV=local` и `APP_ENV=test` пустой `MAX_WEBHOOK_SECRET` разрешен для разработки и тестов. В `APP_ENV=production` пустой `MAX_WEBHOOK_SECRET` не блокирует запуск, но backend логирует warning при старте приложения.

## Bitrix24

- `BITRIX24_ENABLED` — включает Bitrix24 Connector MVP. По умолчанию для production-пилота оставьте `false`, если реальный webhook не настроен.
- `BITRIX24_WEBHOOK_URL` — webhook URL или иной secret интеграции. Реальное значение не коммитить и не выводить в логи.
- `BITRIX24_REQUEST_TIMEOUT_SECONDS` — timeout исходящих запросов к Битрикс24, когда интеграция включена.
- `BITRIX24_SYNC_ON_TASK_CREATE` — флаг автоматической синхронизации после создания задачи. В `v1.0.0` автоматические triggers не подключены, оставьте `false`.
- `BITRIX24_SYNC_ON_STATUS_CHANGE` — флаг автоматической синхронизации после изменения статуса. В `v1.0.0` оставьте `false`.
- `BITRIX24_SYNC_ON_ACCEPTANCE` — флаг автоматической синхронизации после приемки/отклонения. В `v1.0.0` оставьте `false`.
- `BITRIX24_DEFAULT_RESPONSIBLE_ID` — ID ответственного в Битрикс24 по умолчанию, если user mapping еще не настроен.
- `BITRIX24_DEFAULT_CREATED_BY_ID` — ID постановщика в Битрикс24 по умолчанию.
- `BITRIX24_PROJECT_GROUP_ID` — ID группы/проекта Битрикс24 для задач.
- `BITRIX24_USE_TASK_CONTROL` — включает контроль результата в задачах Битрикс24, если поддержано настройками портала.

Если `BITRIX24_ENABLED=false`, интеграционный слой не должен выполнять внешние HTTP-запросы. Если `BITRIX24_ENABLED=true`, `BITRIX24_WEBHOOK_URL` становится обязательным: при пустом значении backend helper возвращает понятную ошибку конфигурации.

В `v1.0.0` Bitrix24 Connector MVP уже включает settings/models/user mapping, REST client, task mapper, manual sync service, ручные sync/status endpoints и WebApp-индикатор в карточке задачи. Автоматические sync triggers остаются выключенными.

## Переменные, которые можно оставить пустыми на MVP

- `MAX_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`
- `BITRIX24_WEBHOOK_URL`

## Предупреждение

Не коммитьте `.env`. Реальные секреты должны храниться только на сервере или в защищенных secret-хранилищах.
