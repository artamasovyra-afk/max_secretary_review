# Первый деплой через GitHub Actions

Документ описывает ручной деплой `max_secretary` на VPS через GitHub Actions workflow.

Workflow запускается только вручную через `workflow_dispatch` и не должен стартовать на каждый push.

## 1. Предварительные условия

На VPS уже должны быть выполнены:

- создан пользователь `deploy`;
- настроен SSH-доступ по ключу;
- установлен Docker;
- репозиторий склонирован в `/opt/max_secretary/app`;
- создан production `.env`;
- пользователь `deploy` имеет доступ к Docker.

Проверка на VPS:

```bash
ssh max-secretary-vps
whoami
cd /opt/max_secretary/app
git status
docker compose -f docker-compose.prod.yml ps
```

Ожидаемо: пользователь `deploy`, проект находится в `/opt/max_secretary/app`.

## 2. GitHub Secrets

В GitHub repository settings должны быть заданы secrets:

- `SSH_HOST`
- `SSH_USER`
- `SSH_PORT`
- `SSH_PRIVATE_KEY`
- `DEPLOY_PATH`

Путь:

```text
Repository -> Settings -> Secrets and variables -> Actions -> New repository secret
```

`SSH_PRIVATE_KEY` нельзя коммитить или выводить в логи.

## 3. Backup Перед Обновлением

Перед деплоем новой версии сделать backup PostgreSQL на VPS:

```bash
ssh max-secretary-vps
cd /opt/max_secretary/app
scripts/ops/backup_postgres.sh
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

Backup-файл должен оставаться в `backups/` или внешнем защищенном хранилище и не должен попадать в git.

## 4. Запуск Workflow

В GitHub:

```text
Actions -> Deploy to VPS -> Run workflow
```

Выбрать нужную ветку или tag, если workflow поддерживает выбор ref.

## 5. Что Выполняет Deploy Workflow

Ожидаемая логика workflow:

```bash
cd "$DEPLOY_PATH"
git fetch --all
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -f http://localhost/api/health || curl -f http://localhost:8000/api/health
```

Если проект деплоится строго на release tag, вместо `git pull` на сервере нужно явно переключить ref:

```bash
git fetch --all --tags
git checkout v1.0.0
```

## 6. Миграции

После deploy применить миграции внутри backend container:

```bash
ssh max-secretary-vps
cd /opt/max_secretary/app
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend alembic current
```

## 7. Проверки После Deploy

```bash
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/health
curl -I http://localhost/
curl -I http://localhost/tasks
curl -I http://localhost/dashboard
```

Ожидаемо:

- `backend`, `postgres`, `redis` healthy;
- `worker`, `webapp`, `nginx` Up;
- `/api/health` возвращает `status=ok`;
- WebApp routes возвращают HTTP `200`.

## 8. Smoke Checks

Для release smoke:

```bash
BASE_URL=http://localhost scripts/release/smoke_release_1_0.sh
```

Если `DEV_AUTH_ENABLED=false`, protected Bitrix24 smoke checks могут быть пропущены как ожидаемое secure-поведение.

## 9. Логи

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 worker
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
```

В логах не должны появляться реальные secrets, tokens или webhook URLs.
