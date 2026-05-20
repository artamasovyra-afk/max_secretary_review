# Manual Dependency Update Policy

Документ описывает регламент ручного обновления зависимостей `max_secretary` для обычного production и закрытого контура.

## Цель

Обновления библиотек и базовых images должны выполняться контролируемо, воспроизводимо и с проверяемым результатом. Production-сервер не должен самостоятельно скачивать пакеты из интернета, потому что это нарушает воспроизводимость поставки, усложняет аудит и создает зависимость от внешней сети.

## Кто Утверждает Обновления

Обновления зависимостей утверждаются ответственным за релиз или техническим владельцем проекта. Для закрытого контура дополнительно может требоваться согласование с ответственным за инфраструктуру, информационную безопасность или внутренний registry.

Перед утверждением нужно проверить:

- список обновляемых пакетов;
- причины обновления;
- риски совместимости;
- результаты тестов;
- результаты smoke tests;
- изменения в Docker images;
- checksums и release manifest.

## Где Фиксируется Список Обновлений

Список обновлений фиксируется в:

- pull request или commit description;
- `CHANGELOG.md`;
- `vendor/release/manifest.txt` для offline bundle;
- внутреннем change request или release notes, если такой процесс используется.

## Backend Dependencies

Порядок обновления backend dependencies:

1. Обновить `backend/requirements.txt` или используемый dependency lock.
2. Собрать wheelhouse заново:

```bash
scripts/offline/build_python_wheelhouse.sh
```

3. Прогнать backend checks:

```bash
cd backend
pytest
ruff check .
```

4. Собрать Docker image:

```bash
docker compose -f docker-compose.prod.yml build backend worker
```

5. Прогнать smoke tests:

```bash
scripts/smoke_test_mvp.sh
scripts/smoke_test_webapp.sh
scripts/smoke_test_bitrix24_connector.sh
```

6. Обновить manifest и checksums:

```bash
scripts/offline/build_release_manifest.sh
```

## Frontend Dependencies

Порядок обновления frontend dependencies:

1. Обновить `webapp/package.json` и `webapp/package-lock.json`.
2. Установить зависимости строго по lock-файлу:

```bash
cd webapp
npm ci
```

3. Проверить build:

```bash
npm run build
```

4. Собрать WebApp image:

```bash
docker compose -f docker-compose.prod.yml build webapp
```

5. Прогнать smoke tests:

```bash
scripts/smoke_test_webapp.sh
```

6. Обновить manifest и checksums:

```bash
scripts/offline/build_release_manifest.sh
```

## Docker Images

Порядок обновления Docker images:

1. Обновлять base images вручную.
2. Фиксировать версии в Dockerfile или compose files.
3. Не использовать `latest` для production или offline deployment.
4. Проверять CVE отдельно, если в организации есть внутренний процесс анализа уязвимостей.
5. Пересобрать production images.
6. Сохранить images для закрытого контура:

```bash
scripts/offline/save_docker_images.sh
```

7. Обновить manifest и checksums:

```bash
scripts/offline/build_release_manifest.sh
```

## Почему Production Не Скачивает Пакеты

Production-сервер не должен скачивать пакеты самостоятельно, потому что:

- невозможно гарантировать, что через время будет скачан тот же артефакт;
- внешний package index или registry может быть недоступен;
- пакет может быть удален, заменен или скомпрометирован;
- закрытый контур может не иметь доступа к интернету;
- аудит поставки требует заранее известных checksums и manifest;
- rollback проще, если весь bundle подготовлен заранее.

## Release Gate

Перед production rollout после обновления зависимостей должны пройти:

- backend tests;
- lint checks;
- frontend build;
- Docker Compose config check;
- smoke tests;
- offline manifest/checksum generation;
- проверка, что `.env`, tokens, passwords, SSH credentials и vendor artifacts не попали в git.
