# Установка Docker и Docker Compose

Документ описывает установку Docker и Docker Compose на VPS для проекта `max_secretary`.

## Установка Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker deploy
```

После добавления `deploy` в группу `docker` нужно перелогиниться или выполнить новую SSH-сессию.

## Проверка версии

```bash
docker --version
docker compose version
```

## Проверка Docker

```bash
docker run hello-world
```

## Почему не ставим PostgreSQL/Redis/nginx напрямую

Для проекта `max_secretary` используется Docker Compose. Системные пакеты PostgreSQL, Redis и nginx не устанавливаются напрямую на VPS, потому что проектные сервисы должны запускаться в контейнерах:

- postgres container
- redis container
- nginx container
- backend container
- worker container

Такой подход делает окружение воспроизводимым и отделяет проектные зависимости от базовой системы VPS.
