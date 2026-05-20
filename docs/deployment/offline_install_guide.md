# Offline Install Guide

Документ описывает полный сценарий установки `max_secretary` в закрытом контуре.

## 1. Получить Offline Bundle

Передать offline bundle на сервер через утвержденный канал. Bundle должен содержать:

- `vendor/docker-images/*.tar`;
- `vendor/checksums/SHA256SUMS`;
- `vendor/release/manifest.txt`;
- `docker-compose.offline.yml`;
- `.env.example`;
- `VERSION`;
- `CHANGELOG.md`;
- deployment scripts и документацию.

## 2. Проверить SHA256SUMS

Из корня распакованного bundle:

```bash
sha256sum -c vendor/checksums/SHA256SUMS
```

Если используется macOS или окружение без `sha256sum`:

```bash
shasum -a 256 -c vendor/checksums/SHA256SUMS
```

Все файлы должны получить статус `OK`. Если проверка не проходит, установку нужно остановить до выяснения причины.

## 3. Загрузить Docker Images

```bash
scripts/offline/load_docker_images.sh
```

Проверить, что images появились локально:

```bash
docker images
```

## 4. Создать .env

```bash
cp .env.example .env
nano .env
```

Заполнить обязательные значения для PostgreSQL и backend. Реальные секреты не должны попадать в git или документацию.

## 5. Отключить Внешние Интеграции

Для автономного запуска в закрытом контуре убедиться, что внешние интеграции выключены:

```env
BITRIX24_ENABLED=false
MAX_SENDER_ENABLED=false
AI_ENABLED=false
```

Если в закрытом контуре есть внутренние endpoints для MAX, Bitrix24 или AI-провайдера, включение интеграций должно выполняться отдельным регламентом.

## 6. Запустить Services

```bash
docker compose -f docker-compose.offline.yml up -d
```

Проверить контейнеры:

```bash
docker compose -f docker-compose.offline.yml ps
```

## 7. Применить Миграции

```bash
docker compose -f docker-compose.offline.yml exec backend alembic upgrade head
```

Проверить текущую миграцию:

```bash
docker compose -f docker-compose.offline.yml exec backend alembic current
```

## 8. Проверить Health И WebApp

```bash
curl http://localhost/api/health
curl -I http://localhost/
```

Ожидаемо:

- `/api/health` возвращает `status=ok`;
- `/` возвращает HTTP 200;
- наружу опубликован только nginx на 80 порту.

## 9. Проверить Логи

```bash
docker compose -f docker-compose.offline.yml logs --tail=100 backend
```

При необходимости проверить остальные сервисы:

```bash
docker compose -f docker-compose.offline.yml logs --tail=100 nginx
docker compose -f docker-compose.offline.yml logs --tail=100 postgres
docker compose -f docker-compose.offline.yml logs --tail=100 redis
docker compose -f docker-compose.offline.yml logs --tail=100 worker
docker compose -f docker-compose.offline.yml logs --tail=100 webapp
```

## Troubleshooting

### image not found

Причина: Docker image не загружен или имя/tag не совпадает с `docker-compose.offline.yml`.

Проверить:

```bash
docker images
scripts/offline/load_docker_images.sh
```

### .env missing

Причина: compose ожидает `.env`, но файл не создан.

Исправить:

```bash
cp .env.example .env
nano .env
```

### database connection refused

Причина: backend стартовал раньше PostgreSQL, неверный `DATABASE_URL` или postgres unhealthy.

Проверить:

```bash
docker compose -f docker-compose.offline.yml ps
docker compose -f docker-compose.offline.yml logs --tail=100 postgres
docker compose -f docker-compose.offline.yml logs --tail=100 backend
```

`DATABASE_URL` должен указывать на host `postgres` внутри docker network.

### migrations fail

Причина: backend image не содержит Alembic files, неверный `DATABASE_URL` или БД недоступна.

Проверить:

```bash
docker compose -f docker-compose.offline.yml exec backend ls -la /app/alembic.ini
docker compose -f docker-compose.offline.yml exec backend ls -la /app/alembic
docker compose -f docker-compose.offline.yml exec backend alembic heads
docker compose -f docker-compose.offline.yml exec backend alembic current
```

### port 80 busy

Причина: порт 80 уже занят другим сервисом на сервере.

Проверить:

```bash
sudo ss -tulpn | grep ':80'
```

Остановить конфликтующий сервис или изменить публикацию порта nginx в compose-файле по локальному регламенту.

### permission denied docker

Причина: пользователь не входит в группу `docker` или текущая SSH-сессия не обновила группы.

Проверить:

```bash
id
docker ps
```

После добавления пользователя в группу `docker` нужно перелогиниться.

### frontend routes return 404

Причина: nginx или webapp image не обслуживает SPA fallback.

Проверить:

```bash
curl -I http://localhost/
curl -I http://localhost/dashboard
curl -I http://localhost/tasks
docker compose -f docker-compose.offline.yml logs --tail=100 nginx
docker compose -f docker-compose.offline.yml logs --tail=100 webapp
```

API routes должны проксироваться на backend, а frontend routes должны обслуживаться WebApp.
