# SSH-доступ по ключу

Документ описывает настройку безопасного SSH-доступа к VPS по отдельному ключу для проекта `max_secretary`.

## 1. Генерация отдельного SSH-ключа на локальной машине

```bash
ssh-keygen -t ed25519 -f ~/.ssh/max_secretary_deploy -C "max_secretary_deploy"
```

## 2. Копирование публичного ключа на сервер

```bash
ssh-copy-id -i ~/.ssh/max_secretary_deploy.pub deploy@SERVER_IP
```

## 3. Проверка входа

```bash
ssh -i ~/.ssh/max_secretary_deploy deploy@SERVER_IP
```

## 4. Отключение входа по паролю только после проверки ключа

Перед изменением настроек нужно убедиться, что вход по ключу работает.

```bash
sudo nano /etc/ssh/sshd_config
```

Параметры:

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

## 5. Перезапуск SSH

Перед перезапуском SSH нужно оставить текущую SSH-сессию открытой, чтобы не потерять доступ к серверу.

```bash
sudo systemctl restart ssh
```

## Что нельзя делать

- Не использовать root для деплоя.
- Не хранить приватный ключ в репозитории.
- Не хранить пароль в README.
- Не передавать пароль в GitHub Actions.
- Не включать password login после настройки ключа.
