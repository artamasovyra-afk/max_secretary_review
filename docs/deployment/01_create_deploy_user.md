# Создание deploy-пользователя

Документ описывает базовую подготовку пользователя `deploy` на VPS для проекта `max_secretary`.

Команды выполняются на VPS под `root` или пользователем с `sudo`-правами.

## 1. Создать пользователя deploy

```bash
sudo adduser deploy
```

## 2. Добавить deploy в группы sudo и docker

```bash
sudo usermod -aG sudo deploy
sudo usermod -aG docker deploy
```

Если Docker еще не установлен, группу `docker` можно добавить после установки Docker.

## 3. Создать рабочие директории

```bash
sudo mkdir -p /opt/max_secretary
sudo mkdir -p /opt/max_secretary/backups
sudo mkdir -p /opt/max_secretary/logs
sudo chown -R deploy:deploy /opt/max_secretary
```

## 4. Проверить пользователя

```bash
id deploy
```

## Предупреждение

Не используйте `root` для деплоя проекта. Деплой `max_secretary` должен выполняться от пользователя `deploy`.
