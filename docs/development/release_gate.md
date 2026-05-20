# Release gate

Документ разделяет проверки `max_secretary` на локальные, CI и VPS.

## local-check

Локальная проверка нужна, чтобы быстро поймать ошибки до push.

Команда:

```bash
make local-check
```

Она выполняет:

- `make preflight`
- `make backend-check`
- `make webapp-check`
- `make compose-check`

Если на локальной машине нет `npm` или `docker`, проверка завершится с понятным сообщением. Это означает, что локальное окружение неполное, а не что релиз обязательно сломан.

Отдельные команды:

```bash
make preflight
make backend-check
make webapp-check
make compose-check
```

## ci-check

CI-проверка должна подтверждать, что код собирается в чистом окружении.

Рекомендуемый набор:

```bash
make ci-check
```

Он включает:

- backend tests;
- backend lint;
- WebApp dependency install;
- WebApp production build;
- Docker Compose config validation.

CI не должен требовать production secrets и не должен выполнять deploy.

## vps-check

VPS-проверка подтверждает, что production stack реально работает после deploy.

Команда на VPS из директории проекта:

```bash
cd /opt/max_secretary/app
make vps-check
```

По умолчанию smoke-тесты используют:

```bash
BASE_URL=http://localhost
```

Для другого URL:

```bash
BASE_URL=http://127.0.0.1 make vps-check
```

`vps-check` выполняет:

- `docker compose -f docker-compose.prod.yml config`;
- `scripts/smoke_test_mvp.sh`;
- `scripts/smoke_test_bot_webhook.sh`;
- `scripts/smoke_test_reminders.sh`;
- `scripts/smoke_test_webapp.sh`;
- `scripts/smoke_test_max_sender.sh`.

## Release rule

Production release считается полным только после успешного VPS check.

Локальные проверки и CI подтверждают качество кода и сборки, но не заменяют проверку на VPS, потому что smoke-тесты зависят от реально поднятых контейнеров, nginx routing, `.env`, Docker volumes и сетевого окружения production host.

## BASE_URL для smoke-тестов

Все smoke-скрипты используют:

```bash
BASE_URL="${BASE_URL:-http://localhost}"
```

Примеры:

```bash
BASE_URL=http://localhost scripts/smoke_test_webapp.sh
BASE_URL=http://127.0.0.1 scripts/smoke_test_max_sender.sh
```

Не добавляйте secrets в команды, коммиты или документацию. Если webhook требует secret, передавайте его только через временную переменную окружения shell-сессии.
