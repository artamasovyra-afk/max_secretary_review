# Первый деплой на VPS

Документ описывает первый деплой проекта `max_secretary` на подготовленный VPS.

## 1. Подключиться к VPS

```bash
ssh deploy@SERVER_IP
```

## 2. Перейти в /opt/max_secretary

```bash
cd /opt/max_secretary
```

## 3. Клонировать репозиторий

```bash
git clone https://github.com/artamasovyra-afk/max_secretary.git app
```

## 4. Перейти в проект

```bash
cd /opt/max_secretary/app
```

## 5. Создать .env из примера

```bash
cp .env.example .env
nano .env
```

## 6. Заполнить реальные значения

В `.env` нужно заполнить реальные значения:

- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `MAX_BOT_TOKEN`
- `MAX_WEBHOOK_SECRET`

## 7. Запустить проект

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 8. Проверить запуск

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/health
```

## 9. Посмотреть логи

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

## 10. Остановить проект

```bash
docker compose -f docker-compose.prod.yml down
```

## Типовые проблемы

- `permission denied` при работе с Docker: пользователь `deploy` не добавлен в группу `docker` или SSH-сессия не была обновлена после добавления.
- Порт `80` занят: на сервере уже запущен другой веб-сервер или контейнер, который слушает `80/tcp`.
- `.env` не найден: файл не создан из `.env.example` или находится не в `/opt/max_secretary/app`.
- Backend не видит postgres: проверьте `DATABASE_URL`, имя сервиса `postgres` и статус контейнера `max_secretary_postgres`.
- Healthcheck не проходит: проверьте логи backend, статус контейнеров и доступность маршрута `/api/health`.
