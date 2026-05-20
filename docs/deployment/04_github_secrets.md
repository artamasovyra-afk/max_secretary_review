# GitHub Secrets для деплоя

Документ описывает GitHub Secrets, необходимые для ручного workflow `.github/workflows/deploy.yml`.

## Как добавить secret

Откройте настройки репозитория:

```text
GitHub → repository → Settings → Secrets and variables → Actions → New repository secret
```

## Необходимые secrets

- `SSH_HOST` — IP или домен VPS.
- `SSH_USER` — пользователь `deploy`.
- `SSH_PORT` — SSH порт, обычно `22`.
- `SSH_PRIVATE_KEY` — приватный SSH-ключ для `deploy`-пользователя.
- `DEPLOY_PATH` — путь к проекту на сервере, например `/opt/max_secretary/app`.

## Предупреждения

- `SSH_PRIVATE_KEY` нельзя коммитить.
- `.env` нельзя коммитить.
- root-доступ использовать нельзя.
- deploy workflow запускать вручную.
- Парольный SSH-доступ лучше отключить после проверки ключа.
