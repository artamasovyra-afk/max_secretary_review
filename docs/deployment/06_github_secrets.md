# GitHub Secrets для деплоя на VPS

Документ описывает GitHub Secrets для деплоя проекта `max_secretary` на VPS через GitHub Actions.

## Где добавить secrets

Откройте настройки репозитория:

```text
Repository → Settings → Secrets and variables → Actions → New repository secret
```

## Обязательные secrets

- `SSH_HOST` — IP адрес VPS.
- `SSH_USER` — `deploy`.
- `SSH_PORT` — `22` или другой порт SSH.
- `SSH_PRIVATE_KEY` — приватный ключ `~/.ssh/max_secretary_deploy`.
- `DEPLOY_PATH` — `/opt/max_secretary/app`.

Для `SSH_PRIVATE_KEY` нужно вставлять весь приватный ключ из локального файла deploy-ключа. Не добавляйте его в репозиторий и не пересылайте в чат.

```text
<full private key content from ~/.ssh/max_secretary_deploy>
```

## Дополнительные secrets

- `HEALTHCHECK_URL` — `http://localhost/api/health`.

## MAX Bot API secrets

Для самого `deploy.yml` секреты MAX Bot API не требуются: workflow подключается к VPS и выполняет обновление проекта.

Реальные значения `MAX_BOT_TOKEN` и `MAX_WEBHOOK_SECRET` должны храниться в production `.env` на VPS или в защищенном secret-хранилище, если позже будет добавлено управление `.env` через CI/CD. Не передавайте эти значения в логах и не добавляйте их в README или документацию.

Безопасный режим по умолчанию:

```env
MAX_SENDER_ENABLED=false
```

В этом режиме backend готовит ответы, но реальная отправка сообщений через MAX Bot API выключена.

## Предупреждения

- Не добавлять приватный ключ в репозиторий.
- Не выводить ключ в логи.
- Не добавлять `MAX_BOT_TOKEN` и `MAX_WEBHOOK_SECRET` в репозиторий.
- Не использовать пароль от VPS.
- Не использовать root.
- `deploy.yml` должен запускаться вручную.
