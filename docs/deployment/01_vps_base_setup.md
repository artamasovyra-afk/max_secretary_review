# Базовая подготовка VPS

Документ описывает первичную подготовку чистого VPS под проект `max_secretary`.

Проектные сервисы `max_secretary` должны запускаться через Docker Compose. На VPS не нужно устанавливать Python-библиотеки, Node.js, FastAPI, React, PostgreSQL, Redis и nginx напрямую в систему.

## 1. Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
```

## 2. Установка базовых пакетов

```bash
sudo apt install -y git curl ca-certificates gnupg ufw nano htop unzip jq tree ncdu
```

## 3. Создание пользователя deploy

```bash
sudo adduser deploy
sudo usermod -aG sudo deploy
```

## 4. Создание рабочих папок

```bash
sudo mkdir -p /opt/max_secretary
sudo mkdir -p /opt/max_secretary/backups
sudo mkdir -p /opt/max_secretary/logs
sudo chown -R deploy:deploy /opt/max_secretary
```

## 5. Базовая настройка firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## Что не устанавливаем на VPS напрямую

На VPS не устанавливаем напрямую в систему:

- Python-библиотеки
- FastAPI
- SQLAlchemy
- Alembic
- Node.js
- React
- Vite
- Ant Design
- PostgreSQL
- Redis
- nginx
- Celery

Все эти компоненты должны находиться внутри Docker-контейнеров и запускаться через Docker Compose.
