# Operator Guide

Документ описывает базовые действия оператора на production VPS `max_secretary`.

## 1. Проверить Сервис

Перейти в директорию проекта:

```bash
cd /opt/max_secretary/app
```

Проверить containers:

```bash
docker compose -f docker-compose.prod.yml ps
```

Ожидаемо:

- `backend`, `postgres`, `redis`, `worker`, `webapp`, `nginx` находятся в состоянии `Up`.
- `backend`, `postgres`, `redis`, `worker`, `webapp`, `nginx` имеют статус `healthy`, если Docker уже успел выполнить healthcheck.
- `nginx` является публичной точкой входа.
- `postgres`, `redis`, `backend`, `worker` и `webapp` не публикуются наружу напрямую.

Проверить health:

```bash
curl http://localhost/api/health
```

Ожидаемо:

```json
{"status":"ok","service":"max_secretary"}
```

## 2. Смотреть Логи

Backend:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

Worker:

```bash
docker compose -f docker-compose.prod.yml logs -f worker
```

В логах worker ожидаемы сообщения:

- `worker started`
- `reminders enabled` или `reminders disabled`
- `Reminder scheduler started`, если `REMINDERS_ENABLED=true`
- `Reminder scheduler disabled by REMINDERS_ENABLED=false`, если напоминания выключены
- `worker stopping` при штатной остановке контейнера

Worker healthcheck проверяет свежий heartbeat-файл внутри контейнера. По умолчанию используется `/tmp/max_secretary_worker_heartbeat`.

Проверить worker healthcheck вручную:

```bash
docker compose -f docker-compose.prod.yml exec worker python -m app.workers.jobs --healthcheck
docker compose -f docker-compose.prod.yml exec worker ls -la /tmp/max_secretary_worker_heartbeat
```

Если `worker` стал `unhealthy`, сначала посмотреть логи:

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 worker
```

Nginx:

```bash
docker compose -f docker-compose.prod.yml logs -f nginx
```

Последние строки без follow:

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 backend
```

## 3. Перезапустить Сервис

Перезапустить backend:

```bash
docker compose -f docker-compose.prod.yml restart backend
```

Перезапустить worker:

```bash
docker compose -f docker-compose.prod.yml restart worker
```

Worker обрабатывает `SIGTERM`/`SIGINT` и должен завершаться корректно. При остановке или пересоздании контейнера в логах должно появиться сообщение `worker stopping`.

После перезапуска проверить:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/health
```

Если после перезапуска `worker`, `webapp` или `nginx` некоторое время показывают `starting`, подождать один интервал healthcheck и повторить `docker compose -f docker-compose.prod.yml ps`.

## 4. Применить Миграции

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Проверить текущую миграцию:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic current
```

## 5. Проверить WebApp

```bash
curl -I http://localhost/
curl -I http://localhost/tasks
curl -I http://localhost/dashboard
```

Ожидаемо: HTTP 200.

## 6. Проверить Bitrix24 Disabled Mode

Если `BITRIX24_ENABLED=false`, ручная синхронизация должна возвращать `disabled`, а реальные HTTP-запросы в Bitrix24 не должны выполняться.

Можно запустить smoke test:

```bash
BASE_URL=http://localhost scripts/smoke_test_bitrix24_connector.sh
```

Ожидаемо:

```text
sync_status=disabled
status_sync_status=disabled
bitrix24_connector_smoke=ok
```

## 7. Сделать Backup

Перед обновлениями и рискованными операциями:

```bash
scripts/ops/backup_postgres.sh
```

Проверить backup:

```bash
ls -lh backups/
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

Подробнее: `docs/operations/backup_restore.md`.

## 8. Обновиться На Новый Tag

Проверить текущую версию:

```bash
git status
git log --oneline -5
cat VERSION
```

Сделать backup:

```bash
scripts/ops/backup_postgres.sh
```

Получить новый tag:

```bash
git fetch --all --tags
git checkout vX.Y.Z
```

Пересобрать и запустить:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Применить миграции:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Проверить:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/health
curl -I http://localhost/
```

Если production policy требует tracking branch вместо detached tag, использовать утвержденный порядок checkout/merge для `main`.

## 9. Что Нельзя Делать

- Редактировать БД руками без backup.
- Коммитить `.env`.
- Коммитить токены, пароли, приватные ключи или webhook URLs.
- Включать внешние интеграции без проверки конфигурации.
- Открывать PostgreSQL наружу.
- Открывать Redis наружу.
- Запускать deploy под `root`, если есть пользователь `deploy`.
- Выполнять destructive git commands без понятного rollback plan.
