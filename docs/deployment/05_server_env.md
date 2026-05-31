# Создание .env на VPS

Документ описывает создание `.env` на VPS для production-запуска проекта `max_secretary`.

`.env` не должен храниться в GitHub.

## Public URLs

Pilot VPS public endpoints:

- WebApp URL: `https://maxsecretary.ru`
- MAX webhook URL: `https://maxsecretary.ru/api/bot/max/webhook`

These URLs are public routing information, not secrets. Real bot tokens and webhook secrets still belong only in the VPS `.env` or a protected secret store.

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
# Header-based dev auth is allowed only in local/test/dev environments.
# With APP_ENV=production, DEV_AUTH_ENABLED=true makes backend startup fail.
DEV_AUTH_ENABLED=false

POSTGRES_DB=max_secretary
POSTGRES_USER=max_secretary
POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD

DATABASE_URL=postgresql+asyncpg://max_secretary:CHANGE_ME_STRONG_PASSWORD@postgres:5432/max_secretary
REDIS_URL=redis://redis:6379/0

MAX_BOT_TOKEN=
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_WEBHOOK_SECRET=
MAX_WEBHOOK_ENABLED=false
MAX_WEBHOOK_DEBUG_LOG=false
MAX_SENDER_ENABLED=false
MAX_INTERACTIVE_RESPONSES_ENABLED=true
MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false
MAX_REQUEST_TIMEOUT_SECONDS=10
MAX_BOT_USERNAME=
TASK_WIZARD_DELETE_USER_INPUTS=false
TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false
TASK_OVERDUE_NOTIFICATION_LOOKBACK_HOURS=6
TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=
WEBAPP_BASE_URL=https://maxsecretary.ru
MAX_WEBAPP_AUTH_ENABLED=false
MAX_WEBAPP_SESSION_SECRET=
MAX_WEBAPP_SESSION_COOKIE_NAME=max_secretary_session
MAX_WEBAPP_SESSION_TTL_SECONDS=86400
MAX_WEBAPP_INITDATA_MAX_AGE_SECONDS=86400
MAX_WEBAPP_COOKIE_SECURE=true
MAX_WEBAPP_COOKIE_SAMESITE=lax
SUPER_ADMIN_LOGIN=
# Set SUPER_ADMIN_PASSWORD and SUPER_ADMIN_SESSION_SECRET only in the VPS .env.
SUPER_ADMIN_SESSION_COOKIE_NAME=max_secretary_super_admin
SUPER_ADMIN_SESSION_TTL_SECONDS=28800
SUPER_ADMIN_COOKIE_SECURE=true
SUPER_ADMIN_COOKIE_SAMESITE=lax

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
- `DEV_AUTH_ENABLED=false`; в `APP_ENV=production` значение `true` запрещено и backend должен завершить старт с ошибкой `DEV_AUTH_ENABLED cannot be true in production`
- `MAX_WEBHOOK_ENABLED=false`, если реальный MAX webhook еще не подключается
- `MAX_SENDER_ENABLED=false`, если real MAX transport должен быть полностью выключен
- `MAX_INTERACTIVE_RESPONSES_ENABLED=true`, чтобы ответы на команды и callback-ответы были разрешены, когда `MAX_SENDER_ENABLED=true`
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false`, пока reminders, пинги и summary не включены отдельным controlled rollout
- `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false`, пока автоматические уведомления о дедлайнах в исходные MAX-чаты не включены отдельным controlled rollout
- `TASK_OVERDUE_NOTIFICATION_LOOKBACK_HOURS=6`, чтобы первое включение не отправило уведомления по старым просроченным задачам
- `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=` пустой в обычном режиме; для controlled rollout можно указать конкретные номера задач, например `53` или `53,54`
- `MAX_WEBHOOK_DEBUG_LOG=false`, если нет временного sandbox/debug-аудита
- `BITRIX24_ENABLED=false`, если реальный Bitrix24 webhook не настроен
- `BITRIX24_WEBHOOK_URL=` пустой, если интеграция выключена
- `MAX_WEBAPP_AUTH_ENABLED=true` включайте только вместе с заполненными `MAX_BOT_TOKEN` и `MAX_WEBAPP_SESSION_SECRET`
- `MAX_WEBAPP_COOKIE_SECURE=true` для HTTPS production
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
- `MAX_WEBHOOK_DEBUG_LOG` — временно включает безопасное логирование структуры webhook event для sandbox-аудита. В production по умолчанию должно быть `false`.
- `MAX_SENDER_ENABLED` — master-switch transport для реальных исходящих запросов через MAX Bot API.
- `MAX_INTERACTIVE_RESPONSES_ENABLED` — разрешает ответы на прямые действия пользователя: `/дьяк`, `/задача`, picker-сообщения и callback answers. Работает только если `MAX_SENDER_ENABLED=true`.
- `MAX_BACKGROUND_NOTIFICATIONS_ENABLED` — разрешает фоновые уведомления: chat deadline reminders (`task_due_in_1h`, `task_overdue`), `/пинг` для другого исполнителя, daily summaries и group sends. Работает только если `MAX_SENDER_ENABLED=true`; при `false` delivery пишется как `skipped/background_disabled`, MAX API не вызывается.
- `MAX_REQUEST_TIMEOUT_SECONDS` — timeout исходящих MAX API запросов.
- `MAX_BOT_USERNAME` — технический username MAX-бота без `@`, например `secretary_oren_bot`. Он не меняется при внешнем ребрендинге `Дьяк` и используется для deep links вида `https://max.ru/<bot_username>?startapp=home`; если не задан, WebApp-кнопки используют plain `WEBAPP_BASE_URL` fallback.
- `TASK_WIZARD_DELETE_USER_INPUTS` — включает best-effort удаление пользовательских сообщений wizard `/задача` после успешного создания задачи. По умолчанию `false`; включайте в production только после controlled live-проверки прав MAX на удаление сообщений. Исходное reply-сообщение и финальная карточка задачи не удаляются.
  - Live MAX check on 2026-05-29 confirmed deletion in one controlled task-creation flow on the production VPS, so production may keep this flag at `true` while monitoring sanitized cleanup errors.
- `TASK_DEADLINE_CHAT_REMINDERS_ENABLED` — включает автоматические уведомления в исходный MAX-чат задачи за 1 час до дедлайна и при наступлении дедлайна. Это feature flag внутри master-switch `MAX_BACKGROUND_NOTIFICATIONS_ENABLED`; оба значения должны быть `true`, иначе MAX API не вызывается. Даже при включенных global flags scheduler отправляет дедлайн-уведомления только в active-чаты с `Chat.settings.deadline_reminders_enabled=true`.
- `TASK_OVERDUE_NOTIFICATION_LOOKBACK_HOURS` — ограничивает окно для `task_overdue`, чтобы при первом включении не отправить уведомления по всем старым просроченным задачам. По умолчанию `6`.
- `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS` — optional allowlist для scheduler-based deadline reminders. Пустое значение означает обычное поведение. Значение `53` обрабатывает только задачу `#53`; `53,54,55` — только эти задачи. Используйте только для controlled rollout/test mode, не как постоянную бизнес-логику. Невалидные значения приводят к ошибке конфигурации, чтобы не перейти случайно в массовый режим.
- `WEBAPP_BASE_URL` — публичный URL WebApp.
- `MAX_WEBAPP_AUTH_ENABLED` — включает backend MAX WebApp auth через проверку `initData`.
- `MAX_WEBAPP_SESSION_SECRET` — отдельный секрет подписи WebApp session cookie. Не используйте `MAX_BOT_TOKEN` как session secret.
- `MAX_WEBAPP_SESSION_COOKIE_NAME` — имя httpOnly cookie, по умолчанию `max_secretary_session`.
- `MAX_WEBAPP_SESSION_TTL_SECONDS` — срок жизни WebApp session cookie.
- `MAX_WEBAPP_INITDATA_MAX_AGE_SECONDS` — максимальный возраст MAX `initData` при обмене на session.
- `MAX_WEBAPP_COOKIE_SECURE` — должен быть `true` в HTTPS production.
- `MAX_WEBAPP_COOKIE_SAMESITE` — по умолчанию `lax`.
- `SUPER_ADMIN_LOGIN` — login отдельного web super-admin интерфейса `/super-admin`.
- `SUPER_ADMIN_PASSWORD` — пароль super-admin. Не коммитить, не выводить в логи, не хранить во frontend.
- `SUPER_ADMIN_SESSION_SECRET` — отдельный секрет подписи super-admin session cookie. Не используйте bot token или WebApp session secret.
- `SUPER_ADMIN_SESSION_COOKIE_NAME` — имя httpOnly cookie super-admin контура, по умолчанию `max_secretary_super_admin`.
- `SUPER_ADMIN_SESSION_TTL_SECONDS` — срок жизни super-admin session cookie.
- `SUPER_ADMIN_COOKIE_SECURE` — должен быть `true` в HTTPS production.
- `SUPER_ADMIN_COOKIE_SAMESITE` — по умолчанию `lax`.

Super-admin web не использует MAX `initData`. Если `SUPER_ADMIN_LOGIN`, `SUPER_ADMIN_PASSWORD` или `SUPER_ADMIN_SESSION_SECRET` не заданы, `/api/super-admin/login` возвращает ошибку конфигурации, но остальные сервисы продолжают работать.

Для безопасного первого запуска оставьте:

```env
MAX_WEBHOOK_ENABLED=false
MAX_WEBHOOK_DEBUG_LOG=false
MAX_SENDER_ENABLED=false
MAX_INTERACTIVE_RESPONSES_ENABLED=true
MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false
TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false
TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=
```

В этом режиме используется логирующий режим `MaxSender`, а реальные сообщения в MAX не отправляются.

Для живого бота с ответами на команды, но без фоновых рассылок, настройте только в production `.env`:

```env
MAX_WEBHOOK_ENABLED=true
MAX_SENDER_ENABLED=true
MAX_INTERACTIVE_RESPONSES_ENABLED=true
MAX_BACKGROUND_NOTIFICATIONS_ENABLED=false
TASK_DEADLINE_CHAT_REMINDERS_ENABLED=false
TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=
MAX_API_BASE_URL=https://platform-api.max.ru
MAX_WEBHOOK_DEBUG_LOG=false
```

Для controlled deadline notification test временно включайте `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true` и `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true` только вместе с allowlist/rate-limit/dry-run планом. Сначала создавайте свежую тестовую задачу с близким дедлайном, задавайте `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=<task_number>`, проверяйте дедупликацию, затем сразу возвращайте фоновые флаги и allowlist в безопасное состояние. Не включайте эти флаги вслепую на весь backlog старых overdue-задач. Если preflight показывает несколько eligible overdue-задач внутри текущего lookback-окна, не открывайте глобальный scheduler window без allowlist.

Live production check on 2026-05-30 confirmed the scheduler path with `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=57`: one overdue notification was sent for the allowlisted task, other overdue candidates were not notified, and the flags were returned to `false` with an empty allowlist after the test.

Live production check on 2026-05-30 also confirmed the due-in-one-hour scheduler path with `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS=60`: one `task_due_in_1h` notification was sent for the allowlisted task, overdue candidates were reduced to zero by the allowlist, no duplicate was sent after another scheduler interval, and the flags were returned to `false` with an empty allowlist after the test.

Live production check on 2026-05-31 confirmed per-chat rollout gating: defaults were disabled for all active chats, one active chat was enabled through `/super-admin`, one allowlisted overdue notification was sent for task `#61`, no other chats received overdue sends during the test window, and the global flags were returned to `false` with an empty allowlist after the test.

Live production recheck on 2026-05-31 confirmed the same per-chat gate on active opt-in chat `Тест ДЬЯК`: with allowlist `73`, the scheduler sent one `task_overdue` notification for task `#73`, other overdue candidates were skipped by allowlist, no duplicate was sent after another scheduler interval, and the global flags were returned to `false` with an empty allowlist after the test.

Production opt-in mode started on 2026-05-31 with `MAX_BACKGROUND_NOTIFICATIONS_ENABLED=true`, `TASK_DEADLINE_CHAT_REMINDERS_ENABLED=true`, and an empty `TASK_DEADLINE_REMINDER_ALLOWED_TASK_NUMBERS`. At start, only active chat `Тест ДЬЯК` had `Chat.settings.deadline_reminders_enabled=true`; the first monitoring window sent 5 overdue notifications only to that chat, with no duplicate or non-opt-in chat deliveries. Keep future chat rollout controlled through the `/super-admin` per-chat toggle.

Также задайте реальные значения только в VPS `.env` или защищенном secret store:

- `MAX_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`
- `MAX_WEBAPP_SESSION_SECRET`, если `MAX_WEBAPP_AUTH_ENABLED=true`

Не коммитьте эти значения, не вставляйте их в README/docs, не присылайте в чат и не добавляйте в скриншоты.

Поведение security hardening:

- `MAX_WEBHOOK_ENABLED=false` отключает `POST /api/bot/max/webhook`: endpoint возвращает `404`, событие не обрабатывается.
- `APP_ENV=production`, `MAX_WEBHOOK_ENABLED=true`, пустой `MAX_WEBHOOK_SECRET`: endpoint возвращает `503 MAX webhook is not configured`, событие не обрабатывается.
- Если `MAX_WEBHOOK_SECRET` задан, request должен содержать header `X-Max-Webhook-Secret`.
- Missing/invalid `X-Max-Webhook-Secret` возвращает `401`.
- Valid `X-Max-Webhook-Secret` принимает payload и передает его в обработчик.
- `MAX_WEBHOOK_DEBUG_LOG=false` должен оставаться production default; включайте debug logging только временно для sandbox-аудита.

В `APP_ENV=local` и `APP_ENV=test` пустой `MAX_WEBHOOK_SECRET` разрешен для разработки и тестов. Если реальный MAX webhook еще не подключается, оставьте `MAX_WEBHOOK_ENABLED=false`.

Sandbox-порядок после модерации тестового бота:

1. Добавить bot credential и webhook secret только в VPS `.env`.
2. Перезапустить backend/worker.
3. Настроить webhook в MAX ЛК на `https://maxsecretary.ru/api/bot/max/webhook`.
4. Отправить обычное сообщение.
5. Отправить reply `/задача`.
6. Проверить callback.
7. Проверить DM/fallback.
8. Обновить `docs/integrations/max_sandbox_audit.md` sanitized результатами.

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
