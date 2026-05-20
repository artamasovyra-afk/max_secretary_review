# Smoke Test WebApp

Документ описывает smoke-тест WebApp после production-деплоя на VPS.

Скрипт `scripts/smoke_test_webapp.sh` проверяет, что nginx корректно маршрутизирует frontend и backend:

- `/` возвращает WebApp;
- `/dashboard` возвращает WebApp fallback для прямого открытия frontend route;
- `/tasks` возвращает WebApp fallback для прямого открытия frontend route;
- `/api/health` проксируется в backend;
- `/openapi.json` проксируется в backend.
- создается тестовая задача;
- `/tasks/{task_id}` открывается как frontend route;
- `GET /api/integrations/bitrix24/tasks/{task_id}/status` возвращает один из статусов `disabled`, `pending`, `synced`, `error`, если dev header auth включен.
- Если `DEV_AUTH_ENABLED=false`, protected Bitrix24 status endpoint может вернуть `401 Header auth is disabled`; для production smoke это считается ожидаемым security-поведением.

## Запуск на VPS

```bash
ssh max-secretary-vps
cd /opt/max_secretary/app
bash scripts/smoke_test_webapp.sh
```

По умолчанию используется:

```bash
BASE_URL=http://localhost
```

Для другого адреса:

```bash
BASE_URL=http://localhost bash scripts/smoke_test_webapp.sh
```

## Требования

На VPS должны быть доступны:

- `curl`;
- `jq`;
- запущенный production stack `docker compose -f docker-compose.prod.yml up -d`;
- внешний nginx-контейнер должен публиковать порт `80`.

## Ожидаемый результат

Route/API проверки должны вернуть HTTP `200`, а создание smoke-данных должно вернуть HTTP `201`.

API routes не должны уходить во frontend, а frontend routes должны открываться напрямую через WebApp fallback.

Bitrix24 sync status API не требует реального Bitrix24 webhook. В окружении без включенной интеграции ожидаемым результатом может быть `pending` или `disabled`. В production с выключенным dev auth допустим результат `auth_disabled`.

Скрипт не содержит секретов и не читает `.env`.
