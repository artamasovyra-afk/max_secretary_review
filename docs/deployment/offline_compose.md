# Offline Docker Compose

Документ описывает запуск `max_secretary` в закрытом контуре из заранее загруженных Docker images.

## Назначение

`docker-compose.offline.yml` не использует `build`. Все сервисы запускаются только из images, которые заранее подготовлены, переданы в закрытый контур и загружены через `docker load`.

## Images

Offline compose ожидает images:

- `max_secretary_backend:${RELEASE_VERSION:-1.0.0}`
- `max_secretary_webapp:${RELEASE_VERSION:-1.0.0}`
- `postgres:16`
- `redis:7`
- `nginx:stable`

Если `RELEASE_VERSION` не задан, Docker Compose использует `1.0.0`.

## Загрузка Images

Если bundle содержит `vendor/docker-images/*.tar`, загрузить images:

```bash
scripts/offline/load_docker_images.sh
```

Или вручную:

```bash
docker load -i vendor/docker-images/max_secretary_backend_1.0.0.tar
docker load -i vendor/docker-images/max_secretary_webapp_1.0.0.tar
docker load -i vendor/docker-images/postgres_16.tar
docker load -i vendor/docker-images/redis_7.tar
docker load -i vendor/docker-images/nginx_stable.tar
```

`load_docker_images.sh` загружает все `.tar` из `vendor/docker-images/`. Для следующих релизов важно передать тот же `RELEASE_VERSION` на этапе запуска `docker compose`, чтобы compose искал правильные backend/webapp image tags.

Проверить:

```bash
docker images
```

## Создание .env

На сервере закрытого контура:

```bash
cp .env.example .env
nano .env
```

Заполнить production values без коммита `.env` в git. Внешние интеграции можно оставить отключенными:

```env
MAX_SENDER_ENABLED=false
BITRIX24_ENABLED=false
```

## Запуск

```bash
docker compose -f docker-compose.offline.yml up -d
```

Для версии, отличной от `1.0.0`:

```bash
RELEASE_VERSION=1.0.1 docker compose -f docker-compose.offline.yml up -d
```

Наружу публикуется только `nginx:80`. PostgreSQL и Redis не публикуют порты наружу.

## Healthchecks

Offline compose повторяет production healthchecks для базовых сервисов:

- `postgres` проверяется через `pg_isready`;
- `redis` проверяется через `redis-cli ping`;
- `backend` проверяет `GET /api/health`;
- `worker` проверяет свежий heartbeat легким healthcheck без импорта scheduler-модулей;
- `webapp` проверяет nginx pid/process/config внутри webapp image;
- `nginx` проверяет nginx pid/process/config.

`backend`, `worker`, `webapp` и `nginx` стартуют с учетом `service_healthy` зависимостей там, где это нужно для корректного порядка запуска.

## Миграции

После старта применить миграции внутри backend container:

```bash
docker compose -f docker-compose.offline.yml exec backend alembic upgrade head
```

## Проверка

```bash
docker compose -f docker-compose.offline.yml ps
curl http://localhost/api/health
```

Ожидаемо:

```json
{"status":"ok","service":"max_secretary"}
```

Фактическое значение `service` зависит от `APP_NAME` в `.env`.

## Проверка Compose Config

В среде, где доступен Docker:

```bash
docker compose -f docker-compose.offline.yml config
```

Если Docker недоступен локально, эту проверку нужно выполнить на VPS, CI runner или в подготовленной offline-сборочной среде.

Для release `v1.0.0` переменную можно не задавать. Если bundle собран с другим `RELEASE_VERSION`, передайте эту же переменную при `docker compose config`, `up`, `ps`, `logs` и `exec`, чтобы compose искал правильные backend/webapp image tags.
