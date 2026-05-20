# Установка базовых пакетов и Docker

Документ описывает установку базовых пакетов и Docker на VPS для проекта `max_secretary`.

## Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
```

## Установка базовых пакетов

```bash
sudo apt install -y git curl ca-certificates gnupg ufw nano htop unzip jq tree ncdu
```

## Установка Docker

```bash
curl -fsSL https://get.docker.com | sh
```

## Добавить deploy в docker

```bash
sudo usermod -aG docker deploy
```

После добавления `deploy` в группу `docker` нужно перелогиниться.

## Проверка

```bash
docker --version
docker compose version
docker run hello-world
```

## Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## Что не ставим напрямую на VPS

PostgreSQL, Redis, nginx, Python-зависимости и Node-зависимости не устанавливаются напрямую на VPS. Они запускаются через Docker Compose.
