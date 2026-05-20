# Offline Bundle

Документ является короткой навигацией по offline-поставке `max_secretary` для закрытого контура.

Подробные инструкции находятся в отдельных `offline_*` документах.

## 1. Политика Поставки

Принципы закрытого контура описаны в:

```text
docs/deployment/offline_delivery_policy.md
```

Ключевые правила:

- production-сервер не скачивает зависимости из интернета;
- Docker images готовятся заранее;
- Python wheels готовятся заранее;
- `.env` создается на сервере и не коммитится;
- внешние интеграции выключены, если нет внутренних endpoints.

## 2. Сборка Offline Bundle

В среде сборки с доступом к Docker и package registries:

```bash
scripts/offline/build_offline_bundle.sh
```

Для релиза `v1.0.0` при сохранении Docker images используйте соответствующую версию:

```bash
RELEASE_VERSION=1.0.0 scripts/offline/save_docker_images.sh
```

Проверить shell scripts:

```bash
bash -n scripts/offline/*.sh
```

## 3. Состав Bundle

Ожидаемая структура:

```text
vendor/
  python-wheels/
  npm-cache/
  docker-images/
  checksums/
  release/
```

В git содержимое `vendor/*` не коммитится, кроме служебных файлов для сохранения структуры каталогов.

## 4. Manifest И Checksums

Создать manifest и checksums:

```bash
scripts/offline/build_release_manifest.sh
```

Проверить после переноса:

```bash
sha256sum -c vendor/checksums/SHA256SUMS
```

или:

```bash
shasum -a 256 -c vendor/checksums/SHA256SUMS
```

## 5. Загрузка Images В Закрытом Контуре

```bash
scripts/offline/load_docker_images.sh
docker images
```

Имена image tags должны совпадать с `docker-compose.offline.yml`.

## 6. Создание .env

```bash
cp .env.example .env
nano .env
```

Для автономного режима:

```env
MAX_SENDER_ENABLED=false
BITRIX24_ENABLED=false
AI_ENABLED=false
```

## 7. Запуск Offline Compose

```bash
docker compose -f docker-compose.offline.yml config
docker compose -f docker-compose.offline.yml up -d
docker compose -f docker-compose.offline.yml ps
```

Наружу публикуется только `nginx:80`; PostgreSQL и Redis не публикуются наружу.

## 8. Миграции

```bash
docker compose -f docker-compose.offline.yml exec backend alembic upgrade head
docker compose -f docker-compose.offline.yml exec backend alembic current
```

## 9. Smoke Checks

```bash
curl http://localhost/api/health
curl -I http://localhost/
curl -I http://localhost/tasks
curl -I http://localhost/dashboard
```

Если smoke scripts входят в bundle:

```bash
BASE_URL=http://localhost scripts/release/smoke_release_1_0.sh
```

## 10. Связанные Документы

- `docs/deployment/offline_bundle_build.md`
- `docs/deployment/offline_compose.md`
- `docs/deployment/offline_docker_images.md`
- `docs/deployment/offline_install_guide.md`
- `docs/deployment/offline_manifest_checksums.md`
- `docs/deployment/offline_python_wheelhouse.md`
