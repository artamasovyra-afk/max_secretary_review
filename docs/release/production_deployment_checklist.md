# Production Deployment Checklist

Чеклист используется перед production deployment или обновлением `max_secretary` на VPS.

## 1. Git

- [ ] Нужный release tag существует.
- [ ] `git status` показывает clean working tree.
- [ ] `VERSION` соответствует release.
- [ ] `CHANGELOG.md` содержит запись release.
- [ ] В git не попали `.env`, секреты, приватные ключи и vendor artifacts.

## 2. VPS

- [ ] SSH key работает.
- [ ] Для deploy используется пользователь `deploy`, не `root`.
- [ ] Docker доступен пользователю `deploy`.
- [ ] Порты `80` и `443` открыты, если они нужны для deployment.
- [ ] PostgreSQL не опубликован наружу.
- [ ] Redis не опубликован наружу.
- [ ] `ufw status` проверен.
- [ ] `ss -tulpn` проверен на неожиданные listening ports.

## 3. Env

- [ ] `.env` создан на VPS.
- [ ] Реальные секреты не хранятся в git.
- [ ] `BITRIX24_ENABLED=false`, если реального webhook нет.
- [ ] `MAX_SENDER_ENABLED=false`, если реальная отправка в MAX не включена.
- [ ] `AI_ENABLED=false`, если AI-интеграции не используются.
- [ ] `DATABASE_URL` указывает на host `postgres` внутри Docker network.
- [ ] `REDIS_URL` указывает на host `redis` внутри Docker network.

## 4. Docker

- [ ] `docker compose -f docker-compose.prod.yml config` прошел успешно.
- [ ] `docker compose -f docker-compose.prod.yml up -d --build` выполнен.
- [ ] Backend container `Up` и `healthy`.
- [ ] PostgreSQL container `Up` и `healthy`.
- [ ] Redis container `Up` и `healthy`.
- [ ] Worker container `Up`.
- [ ] WebApp container `Up`.
- [ ] Nginx container `Up`.

## 5. DB

- [ ] Миграции применены:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

- [ ] `alembic current` соответствует `head`:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic heads
docker compose -f docker-compose.prod.yml exec backend alembic current
```

## 6. Smoke

- [ ] Health endpoint работает:

```bash
curl http://localhost/api/health
```

- [ ] WebApp routes работают:

```bash
curl -I http://localhost/
curl -I http://localhost/tasks
curl -I http://localhost/dashboard
```

- [ ] MVP smoke passed:

```bash
BASE_URL=http://localhost scripts/smoke_test_mvp.sh
```

- [ ] Bitrix24 disabled smoke passed:

```bash
BASE_URL=http://localhost scripts/smoke_test_bitrix24_connector.sh
```

- [ ] Reminders smoke passed:

```bash
BASE_URL=http://localhost scripts/smoke_test_reminders.sh
```

## 7. Backup

- [ ] Backup сделан перед обновлением:

```bash
scripts/ops/backup_postgres.sh
```

- [ ] Backup файл существует в `backups/`.
- [ ] Backup проходит проверку:

```bash
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

## 8. Rollback

- [ ] Предыдущий release tag известен.
- [ ] Backup доступен.
- [ ] Restore инструкция доступна:

```text
docs/operations/backup_restore.md
```

- [ ] Порядок rollback согласован:
  - checkout предыдущего tag;
  - rebuild/restart compose;
  - restore DB при необходимости;
  - smoke tests после rollback.
