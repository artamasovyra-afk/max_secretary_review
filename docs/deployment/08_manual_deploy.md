# Ручной деплой

Документ описывает ручной деплой `max_secretary` на VPS без GitHub Actions.

Команды выполняются под пользователем `deploy`.

## 1. Подключиться К VPS

```bash
ssh max-secretary-vps
cd /opt/max_secretary/app
```

Проверить пользователя и состояние git:

```bash
whoami
pwd
git status
git log --oneline -5
cat VERSION
```

Ожидаемо:

- `whoami` возвращает `deploy`;
- `pwd` возвращает `/opt/max_secretary/app`;
- working tree clean.

## 2. Backup Перед Обновлением

Перед обновлением production stack сделать backup PostgreSQL:

```bash
scripts/ops/backup_postgres.sh
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

Backup не коммитится в git. Желательно скопировать backup во внешнее защищенное хранилище.

## 3. Обновить Код

Для обновления до текущего `main`:

```bash
git fetch --all
git pull
```

Для пилотного релиза `v1.0.0`:

```bash
git fetch --all --tags
git checkout v1.0.0
```

Проверить:

```bash
git status
git describe --tags --exact-match HEAD || true
git rev-parse HEAD
cat VERSION
```

## 4. Проверить Docker Compose Config

```bash
docker compose -f docker-compose.prod.yml config
```

Если config не проходит, deploy нужно остановить и исправить compose/env до запуска контейнеров.

## 5. Запустить Production Stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Проверить контейнеры:

```bash
docker compose -f docker-compose.prod.yml ps
```

Ожидаемо:

- `backend` Up / healthy;
- `postgres` Up / healthy;
- `redis` Up / healthy;
- `worker` Up;
- `webapp` Up;
- `nginx` Up.

## 6. Применить Миграции

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend alembic current
```

Alembic files должны быть внутри backend image:

```bash
docker compose -f docker-compose.prod.yml exec backend ls -la /app/alembic.ini
docker compose -f docker-compose.prod.yml exec backend ls -la /app/alembic
```

## 7. Health И WebApp Checks

```bash
curl http://localhost/api/health
curl -I http://localhost/
curl -I http://localhost/tasks
curl -I http://localhost/dashboard
curl -I http://localhost/openapi.json
```

Ожидаемо:

- `/api/health` возвращает `status=ok`;
- WebApp routes возвращают HTTP `200`;
- `/openapi.json` возвращает HTTP `200`.

## 8. Smoke Checks

```bash
BASE_URL=http://localhost scripts/release/smoke_release_1_0.sh
```

Можно запускать отдельные smoke scripts:

```bash
BASE_URL=http://localhost scripts/smoke_test_mvp.sh
BASE_URL=http://localhost scripts/smoke_test_webapp.sh
BASE_URL=http://localhost scripts/smoke_test_bitrix24_connector.sh
BASE_URL=http://localhost scripts/smoke_test_reminders.sh
```

## 9. Логи

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 worker
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
docker compose -f docker-compose.prod.yml logs --tail=100 postgres
docker compose -f docker-compose.prod.yml logs --tail=100 redis
```

В логах не должны выводиться production secrets.

## 10. Rollback

Минимальный rollback-порядок:

1. Зафиксировать текущую ошибку и логи.
2. Переключиться на предыдущий известный tag:

```bash
git fetch --all --tags
git checkout vPREVIOUS
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

3. Проверить health и smoke.
4. Restore backup выполнять только при подтвержденной необходимости и по инструкции `docs/operations/backup_restore.md`.
