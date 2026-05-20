# Offline Manifest And Checksums

Документ описывает manifest и checksum tooling для offline bundle `max_secretary`.

## Зачем Нужны Checksums

Checksums нужны, чтобы проверить целостность поставки после передачи в закрытый контур. Они помогают обнаружить:

- повреждение файлов при копировании;
- неполную поставку;
- замену Docker image archive;
- несовпадение версии release files.

## Создание Manifest И Checksums

Из корня репозитория:

```bash
scripts/offline/build_release_manifest.sh
```

Скрипт создает:

```text
vendor/release/manifest.txt
vendor/checksums/SHA256SUMS
```

В manifest и checksums попадают:

- `vendor/docker-images/*.tar`;
- `vendor/python-wheels/*`;
- `docker-compose.offline.yml`;
- `.env.example`;
- `VERSION`;
- `CHANGELOG.md`.

На Linux используется `sha256sum`, если он доступен. На macOS используется fallback:

```bash
shasum -a 256
```

## Проверка На Linux

Из корня распакованного bundle:

```bash
sha256sum -c vendor/checksums/SHA256SUMS
```

## Проверка На macOS

```bash
shasum -a 256 -c vendor/checksums/SHA256SUMS
```

## Ожидаемый Результат

Каждый файл должен получить статус `OK`. Если проверка падает, bundle нельзя использовать для production deployment до выяснения причины.

## Git Policy

`vendor/checksums/*` и `vendor/release/*` относятся к release artifacts и обычно не коммитятся в git. В репозитории можно хранить только служебные файлы или документацию, если нужно зафиксировать структуру каталогов.
