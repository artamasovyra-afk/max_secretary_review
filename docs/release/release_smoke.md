# Release Smoke

Документ описывает общий smoke-тест для пилотной версии `max_secretary` 1.0.0.

## Назначение

`scripts/release/smoke_release_1_0.sh` запускает основные smoke scripts, которые проверяют production deployment после сборки или обновления.

Скрипт не требует реальных Bitrix24 или MAX секретов. Bitrix24 проверяется в disabled mode, если dev header auth включен для окружения. Если `DEV_AUTH_ENABLED=false`, protected Bitrix24 checks считаются закрытыми корректно и помечаются как skipped.

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

Скрипт запускает:

- `scripts/smoke_test_mvp.sh`;
- `scripts/smoke_test_webapp.sh`;
- `scripts/smoke_test_bitrix24_connector.sh`;
- `scripts/smoke_test_reminders.sh`, если файл существует и исполняемый.

## Требования

На машине должны быть доступны:

- `curl`;
- `jq`;
- работающий backend/WebApp по `BASE_URL`;
- production database с примененными миграциями.
- для полной Bitrix24 disabled smoke-проверки нужен dev auth context через headers; в production с `DEV_AUTH_ENABLED=false` protected checks могут быть пропущены как ожидаемое security-поведение.

## Ожидаемый Результат

В конце успешного выполнения:

```text
release_smoke=ok
```

Если любой smoke script завершится ошибкой, общий release smoke остановится с ненулевым exit code.
