# Offline Docker Images

Документ описывает подготовку Docker images для поставки `max_secretary` в закрытый контур.

## Назначение

Production-сервер в закрытом контуре не должен скачивать Docker images из Docker Hub или других внешних registry. Все images собираются или скачиваются заранее в подготовленной среде, сохраняются в `.tar` архивы и передаются через утвержденный канал.

## Сохранение Images

Из корня репозитория:

```bash
scripts/offline/save_docker_images.sh
```

Скрипт:

- проверяет наличие `docker`;
- создает `vendor/docker-images`;
- выполняет `docker compose -f docker-compose.prod.yml build`;
- определяет локальные image names для `backend` и `webapp` через `docker compose images`;
- сохраняет backend, webapp, `nginx:stable`, `postgres:16` и `redis:7`.

Архивы сохраняются в:

```text
vendor/docker-images/max_secretary_backend_1.0.0.tar
vendor/docker-images/max_secretary_webapp_1.0.0.tar
vendor/docker-images/nginx_stable.tar
vendor/docker-images/postgres_16.tar
vendor/docker-images/redis_7.tar
```

Версию в имени backend/webapp архивов можно переопределить:

```bash
RELEASE_VERSION=1.0.0 scripts/offline/save_docker_images.sh
```

## Загрузка Images В Закрытом Контуре

После передачи bundle на сервер:

```bash
scripts/offline/load_docker_images.sh
```

Скрипт:

- проверяет наличие `vendor/docker-images`;
- выполняет `docker load -i` для всех `.tar`;
- печатает список Docker images после загрузки.

## Проверка

После загрузки проверить:

```bash
docker images
docker compose -f docker-compose.prod.yml config
```

Если используется отдельный `docker-compose.offline.yml`, он должен ссылаться на загруженные image names и не требовать `build` или внешнего registry.

Для release `v1.0.0` ожидаемые offline image tags:

```text
max_secretary_backend:1.0.0
max_secretary_webapp:1.0.0
```

## Git Policy

Содержимое `vendor/docker-images/*` не коммитится в git. В репозитории сохраняется только `vendor/docker-images/.gitkeep`, чтобы зафиксировать структуру каталога.

Перед коммитом проверить:

```bash
git status --short
```

В staged changes не должны попадать `.tar` archives.
