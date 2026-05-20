# Offline Bundle Build

Документ описывает общий процесс сборки offline bundle для поставки `max_secretary` в закрытый контур.

## Подготовка

Сборку нужно выполнять в среде, где доступны:

- Python, совместимый с backend dependencies;
- pip;
- Docker;
- Docker Compose plugin;
- доступ к Python package index или внутреннему registry;
- доступ к Docker Hub или внутреннему Docker Registry для базовых images.

Сборка не требует root-доступа, но пользователь должен иметь право выполнять Docker commands.

## Запуск

Из корня репозитория:

```bash
scripts/offline/build_offline_bundle.sh
```

По умолчанию bundle собирается с `RELEASE_VERSION=1.0.0`. Для следующего patch release можно явно передать версию:

```bash
RELEASE_VERSION=1.0.1 scripts/offline/build_offline_bundle.sh
```

Если нужно использовать конкретный Python:

```bash
PYTHON_BIN=python3.12 scripts/offline/build_offline_bundle.sh
```

Переменные можно комбинировать:

```bash
RELEASE_VERSION=1.0.1 PYTHON_BIN=python3.12 scripts/offline/build_offline_bundle.sh
```

Скрипт последовательно запускает:

1. `scripts/offline/build_python_wheelhouse.sh`
2. `scripts/offline/save_docker_images.sh`
3. `scripts/offline/build_release_manifest.sh`

Если Docker недоступен, скрипт завершится с ошибкой:

```text
Docker is required to build offline bundle images.
```

## Ожидаемая Структура vendor

После успешной сборки:

```text
vendor/
  python-wheels/
  docker-images/
  checksums/
    SHA256SUMS
  release/
    manifest.txt
```

`vendor/npm-cache/` может быть добавлен отдельным шагом, если frontend build нужно выполнять внутри закрытого контура из локального npm cache или internal registry.

## Перенос В Закрытый Контур

Передача bundle выполняется через утвержденный канал. Минимально нужно передать:

- `vendor/docker-images/*.tar`;
- `vendor/python-wheels/*`;
- `vendor/checksums/SHA256SUMS`;
- `vendor/release/manifest.txt`;
- `docker-compose.offline.yml`;
- `.env.example`;
- `VERSION`;
- `CHANGELOG.md`;
- deployment docs.

После переноса проверить checksums:

```bash
sha256sum -c vendor/checksums/SHA256SUMS
```

На macOS:

```bash
shasum -a 256 -c vendor/checksums/SHA256SUMS
```

## Запуск В Закрытом Контуре

1. Загрузить Docker images:

```bash
scripts/offline/load_docker_images.sh
```

2. Создать `.env`:

```bash
cp .env.example .env
nano .env
```

3. Запустить offline compose:

```bash
docker compose -f docker-compose.offline.yml up -d
```

4. Применить миграции:

```bash
docker compose -f docker-compose.offline.yml exec backend alembic upgrade head
```

5. Проверить health:

```bash
curl http://localhost/api/health
```

Если offline compose запускается для версии, отличной от значения по умолчанию, передайте тот же `RELEASE_VERSION`:

```bash
RELEASE_VERSION=1.0.1 docker compose -f docker-compose.offline.yml up -d
```
