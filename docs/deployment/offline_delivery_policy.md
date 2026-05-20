# Offline Delivery Policy

Проект `max_secretary` должен поддерживать поставку в закрытый контур без доступа production-сервера к интернету. Этот документ фиксирует правила подготовки release bundle и границы ответственности между сборочной средой, утвержденным каналом передачи и production-сервером.

## Цель

Production-сервер в закрытом контуре должен запускать `max_secretary` без скачивания зависимостей, Docker images, frontend packages или внешних артефактов из интернета. Все необходимые компоненты готовятся заранее, проверяются, передаются через утвержденный канал и загружаются локально.

## Принципы

1. Production-сервер не скачивает зависимости из интернета.
2. Все backend dependencies фиксируются в `backend/requirements.txt`.
3. Все frontend dependencies фиксируются через `webapp/package-lock.json`.
4. Docker images собираются заранее и передаются через утвержденный канал.
5. Python wheels готовятся заранее.
6. Frontend build либо собирается заранее, либо собирается из локального npm cache или internal registry.
7. Внешние интеграции должны быть отключаемыми через configuration flags.
8. Bitrix24 и MAX внешние API могут быть недоступны в закрытом контуре.
9. Основной функционал задач должен работать автономно без внешних интеграций.
10. Обновления библиотек выполняются вручную и регламентно.

## Структура Поставки

```text
vendor/
  python-wheels/
  npm-cache/
  docker-images/
  checksums/
  release/
```

Назначение директорий:

- `vendor/python-wheels/` — подготовленный wheelhouse для backend dependencies.
- `vendor/npm-cache/` — локальный npm cache или артефакты для frontend dependency install.
- `vendor/docker-images/` — сохраненные Docker images в формате `.tar`.
- `vendor/checksums/` — checksum-файлы для проверки целостности поставки.
- `vendor/release/` — release manifests, инструкции, версии и сопроводительные файлы поставки.

## Git Policy

Содержимое `vendor/*` не коммитится в git. Исключение допускается только для служебных файлов вроде `README.md` или `.gitkeep`, если они нужны для описания структуры каталогов.

В git не должны попадать:

- Docker image archives;
- Python wheelhouse;
- npm cache;
- production `.env`;
- tokens, passwords, webhook URLs и приватные ключи;
- закрытые release bundles.

## Интеграции В Закрытом Контуре

В закрытом контуре внешние API могут быть недоступны. Поэтому:

- `MAX_SENDER_ENABLED` должен оставаться отключенным, если нет доступного MAX API endpoint.
- `BITRIX24_ENABLED` должен оставаться `false`, если нет доступного Bitrix24 endpoint.
- task workflow не должен падать из-за недоступности внешних интеграций.
- ручная синхронизация интеграций должна возвращать понятный disabled/error статус.

## Release Bundle Requirements

Каждая поставка должна содержать:

- версию приложения;
- commit hash;
- список Docker images;
- checksum-файлы;
- инструкции загрузки Docker images;
- инструкции применения миграций;
- пример `.env` без секретов;
- список внешних интеграций и их режимы работы;
- результат preflight/release checks.

## Обновление Библиотек

Обновления зависимостей выполняются вручную:

1. Обновить версии в исходных lock-файлах.
2. Прогнать тесты и сборку в среде с интернетом или внутренними registry.
3. Пересобрать Python wheels, npm cache и Docker images.
4. Пересчитать checksums.
5. Передать bundle через утвержденный канал.
6. Проверить bundle в закрытом контуре до production rollout.
