# Настройка SSH-доступа по ключу

Документ описывает настройку SSH-доступа по ключу для пользователя `deploy`.

## 1. Генерация ключа на локальной машине

```bash
ssh-keygen -t ed25519 -f ~/.ssh/max_secretary_deploy -C "max_secretary_deploy"
```

## 2. Копирование публичного ключа на VPS

```bash
ssh-copy-id -i ~/.ssh/max_secretary_deploy.pub deploy@VPS_IP
```

## 3. Проверка подключения

```bash
ssh -i ~/.ssh/max_secretary_deploy deploy@VPS_IP
```

## 4. Настройка ~/.ssh/config на локальной машине

```sshconfig
Host max-secretary-vps
    HostName VPS_IP
    User deploy
    Port 22
    IdentityFile ~/.ssh/max_secretary_deploy
```

## 5. Проверка

```bash
ssh max-secretary-vps
```

## 6. Отключение парольного входа после проверки ключа

Перед изменением настроек нужно убедиться, что подключение по ключу работает.

```bash
sudo nano /etc/ssh/sshd_config
```

Параметры:

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

## 7. Перезапуск SSH

Перед перезапуском SSH оставьте активную сессию открытой, чтобы не потерять доступ.

```bash
sudo systemctl restart ssh
```

## Что нельзя делать

- Не класть приватный ключ в репозиторий.
- Не передавать пароль в GitHub Actions.
- Не использовать root для деплоя.
- Не отключать парольный вход до проверки ключа.
