# Offline Deployment

Документ является обзором offline-развертывания `max_secretary` для закрытого контура на базе актуального `v1.0.x` процесса.

Подробные инструкции вынесены в специализированные документы:

- [Offline delivery policy](offline_delivery_policy.md)
- [Offline bundle build](offline_bundle_build.md)
- [Offline Docker images](offline_docker_images.md)
- [Offline Python wheelhouse](offline_python_wheelhouse.md)
- [Offline manifest and checksums](offline_manifest_checksums.md)
- [Offline compose](offline_compose.md)
- [Offline install guide](offline_install_guide.md)
- [Manual dependency update policy](manual_dependency_update_policy.md)

## Цель

Production-сервер в закрытом контуре не должен скачивать зависимости, Docker images или frontend packages из интернета. Все артефакты готовятся заранее в build-среде, проверяются, передаются через утвержденный канал и запускаются локально через `docker-compose.offline.yml`.

## Принципы

- Production-сервер не скачивает зависимости из интернета.
- Backend dependencies фиксируются в `backend/requirements.txt`.
- Frontend dependencies фиксируются через `webapp/package-lock.json`.
- Docker images собираются и сохраняются заранее.
- Python wheelhouse готовится заранее.
- Проверка целостности выполняется через `vendor/checksums/SHA256SUMS`.
- Внешние интеграции должны быть отключаемыми.
- Основной функционал задач должен работать автономно без MAX, Bitrix24 и AI endpoints.

## Структура Offline Bundle

Актуальная структура поставки:

```text
vendor/
  python-wheels/
  npm-cache/
  docker-images/
  checksums/
    SHA256SUMS
  release/
    manifest.txt
```

Назначение:

- `vendor/python-wheels/` — wheelhouse для backend dependencies.
- `vendor/npm-cache/` — локальный npm cache или frontend dependency artifacts, если frontend build выполняется внутри закрытого контура.
- `vendor/docker-images/` — Docker image archives в формате `.tar`.
- `vendor/checksums/` — checksum-файлы для проверки целостности.
- `vendor/release/` — manifest и сопроводительная release-информация.

Содержимое `vendor/*` не коммитится в git, кроме служебных `.gitkeep`/`README.md`, если они нужны для сохранения структуры.

## Сборка Python Wheelhouse

Из корня репозитория в build-среде:

```bash
scripts/offline/build_python_wheelhouse.sh
```

Скрипт выполняет:

```bash
python -m pip wheel -r backend/requirements.txt -w vendor/python-wheels
```

Установка зависимостей без интернета:

```bash
pip install --no-index --find-links=vendor/python-wheels -r backend/requirements.txt
```

## Сохранение Docker Images

В build-среде с Docker:

```bash
RELEASE_VERSION=1.0.0 scripts/offline/save_docker_images.sh
```

Скрипт:

- собирает production images через `docker compose -f docker-compose.prod.yml build`;
- определяет image names для `backend` и `webapp` через `docker compose images`;
- сохраняет backend, webapp, `nginx:stable`, `postgres:16`, `redis:7` в `vendor/docker-images/`.

Ожидаемые archives:

```text
vendor/docker-images/max_secretary_backend_1.0.0.tar
vendor/docker-images/max_secretary_webapp_1.0.0.tar
vendor/docker-images/nginx_stable.tar
vendor/docker-images/postgres_16.tar
vendor/docker-images/redis_7.tar
```

Если используется другой release version, `RELEASE_VERSION` и image tags в `docker-compose.offline.yml` должны быть синхронизированы.

## Загрузка Docker Images В Закрытом Контуре

После переноса bundle:

```bash
scripts/offline/load_docker_images.sh
docker images
```

Скрипт выполняет `docker load -i` для всех `.tar` файлов из `vendor/docker-images/` и выводит список загруженных images.

## Docker Compose Offline

`docker-compose.offline.yml` предназначен для запуска без `build:` и без внешнего registry. Он использует заранее загруженные images:

- backend image;
- worker на том же backend image;
- webapp image;
- `postgres:16`;
- `redis:7`;
- `nginx:stable`.

Проверить compose:

```bash
docker compose -f docker-compose.offline.yml config
```

Запуск:

```bash
docker compose -f docker-compose.offline.yml up -d
docker compose -f docker-compose.offline.yml ps
```

Наружу публикуется только `nginx:80`. PostgreSQL, Redis, backend, worker и webapp не должны публиковаться наружу напрямую.

## Manifest И SHA256SUMS

Сформировать manifest и checksums:

```bash
scripts/offline/build_release_manifest.sh
```

Проверить целостность после переноса:

```bash
sha256sum -c vendor/checksums/SHA256SUMS
```

Если `sha256sum` недоступен:

```bash
shasum -a 256 -c vendor/checksums/SHA256SUMS
```

Если хотя бы один файл не проходит проверку, установку нужно остановить до выяснения причины.

## Установка В Закрытом Контуре

Минимальный порядок:

1. Получить offline bundle через утвержденный канал.
2. Проверить `vendor/checksums/SHA256SUMS`.
3. Загрузить Docker images:

```bash
scripts/offline/load_docker_images.sh
```

4. Создать `.env`:

```bash
cp .env.example .env
nano .env
```

5. Убедиться, что внешние интеграции выключены, если для них нет внутренних endpoints:

```env
BITRIX24_ENABLED=false
MAX_SENDER_ENABLED=false
AI_ENABLED=false
```

6. Запустить stack:

```bash
docker compose -f docker-compose.offline.yml up -d
```

7. Применить миграции:

```bash
docker compose -f docker-compose.offline.yml exec backend alembic upgrade head
docker compose -f docker-compose.offline.yml exec backend alembic current
```

8. Проверить health и WebApp:

```bash
curl http://localhost/api/health
curl -I http://localhost/
curl -I http://localhost/tasks
curl -I http://localhost/dashboard
```

9. Проверить логи:

```bash
docker compose -f docker-compose.offline.yml logs --tail=100 backend
docker compose -f docker-compose.offline.yml logs --tail=100 worker
docker compose -f docker-compose.offline.yml logs --tail=100 nginx
```

## Внешние Интеграции

По умолчанию для закрытого контура внешние интеграции должны быть выключены:

- `BITRIX24_ENABLED=false`;
- `MAX_SENDER_ENABLED=false`;
- `AI_ENABLED=false`.

Если в закрытом контуре есть внутренние endpoints для MAX, Bitrix24 или AI-провайдера, включение выполняется отдельным регламентом с проверкой `.env`, network access, secret handling и smoke tests.

## Сборка Полного Bundle

Общий скрипт:

```bash
scripts/offline/build_offline_bundle.sh
```

Он последовательно запускает:

1. `scripts/offline/build_python_wheelhouse.sh`
2. `scripts/offline/save_docker_images.sh`
3. `scripts/offline/build_release_manifest.sh`

Если Docker недоступен, сборка завершится с понятной ошибкой:

```text
Docker is required to build offline bundle images.
```

## Troubleshooting

Подробный troubleshooting описан в [Offline install guide](offline_install_guide.md).

Типовые проблемы:

- image not found;
- `.env` missing;
- database connection refused;
- migrations fail;
- port 80 busy;
- permission denied docker;
- frontend routes return 404.
