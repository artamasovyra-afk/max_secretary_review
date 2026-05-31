# Release Smoke

Документ описывает общий smoke-тест для пилотной версии `max_secretary` 1.0.0.

## Назначение

`scripts/release/smoke_release_1_0.sh` выполняет безопасную production smoke-проверку после сборки или обновления.

Скрипт не требует реальных Bitrix24 или MAX секретов и не мутирует protected API без сессии. После перехода на production WebApp auth protected endpoints без session cookie должны возвращать `401`; для release smoke это считается успешной security-проверкой.

## Запуск

На VPS из корня проекта:

```bash
scripts/release/smoke_release_1_0.sh
```

По умолчанию используется:

```text
BASE_URL=http://localhost
```

Для проверки удаленного адреса:

```bash
BASE_URL=http://SERVER_IP scripts/release/smoke_release_1_0.sh
```

## Что Проверяется

Скрипт проверяет:

- public API: `GET /api/health`;
- public WebApp routes: `/`, `/tasks`, `/dashboard`, `/group-assignments`, `/settings`, `/site.webmanifest`, `/favicon.ico`;
- protected API without auth: `GET /api/tasks`, `GET /api/tasks/inbox/summary`, `GET /api/users`, `GET /api/chats`, `POST /api/organizations`, `GET /api/auth/me`;
- authenticated API smoke: skipped unless a separate safe session fixture is introduced;
- MAX sender smoke: skipped by default; no real sends;
- Bitrix24/reminders smoke: skipped in production release smoke because protected writes require auth.

## Требования

На машине должны быть доступны:

- `curl`;
- `jq`;
- работающий backend/WebApp по `BASE_URL`;
- production database с примененными миграциями.

Глубокие сценарии из `scripts/smoke_test_mvp.sh`, `scripts/smoke_test_webapp.sh`, `scripts/smoke_test_bitrix24_connector.sh` и `scripts/smoke_test_reminders.sh` остаются полезны для local/test/dev окружений с явным безопасным auth context. Их не следует запускать как production release smoke без session/dev fixture.

## Ожидаемый Результат

В конце успешного выполнения:

```text
release_smoke=ok
public_smoke=ok
protected_unauth_smoke=ok
authenticated_smoke=skipped:no_session
max_sender_smoke=skipped:disabled
bitrix24_smoke=skipped:auth_disabled
reminders_smoke=skipped:no_authenticated_context
```

Если public endpoint недоступен или protected endpoint без auth не возвращает `401`, общий release smoke остановится с ненулевым exit code.
