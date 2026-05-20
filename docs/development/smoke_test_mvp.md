# Smoke Test MVP API

Документ описывает smoke-тест backend MVP API после деплоя на VPS.

Скрипт проверяет основной happy path на PostgreSQL через nginx и `localhost`:

- создание организации;
- создание постановщика, двух исполнителей и наблюдателя;
- создание чата и участников чата;
- создание задачи с двумя исполнителями и одним наблюдателем;
- получение карточки задачи;
- добавление комментария;
- добавление file metadata;
- отправку ответа исполнителем;
- переход задачи в `waiting_acceptance`;
- приемку результата постановщиком;
- переход задачи в `done`;
- свод задач `/api/tasks/inbox/summary` для исполнителя и постановщика.

## Запуск на VPS

```bash
ssh max-secretary-vps
cd /opt/max_secretary/app
bash scripts/smoke_test_mvp.sh
```

По умолчанию скрипт использует:

```bash
BASE_URL=http://localhost
```

Для другого адреса:

```bash
BASE_URL=http://localhost bash scripts/smoke_test_mvp.sh
```

## Требования

На VPS должны быть доступны:

- `curl`;
- `jq`;
- запущенный production stack `docker compose -f docker-compose.prod.yml up -d`;
- примененные Alembic migrations.

## Данные

Скрипт создает тестовые записи в production PostgreSQL с уникальным `RUN_ID`.
Физическая загрузка файлов не выполняется: проверяется только metadata.

Скрипт не содержит секретов и не читает `.env` напрямую.
