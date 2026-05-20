# Security Checklist 1.0.0

Этот checklist используется перед пилотным production-релизом `1.0.0`.
Все пункты нужно проверить на актуальном tag и на VPS под пользователем `deploy`.

## Repository And Secrets

- [ ] `.env` не находится в git.
- [ ] Реальные секреты, токены, пароли и приватные ключи не закоммичены.
- [ ] Секреты не выводятся в логи backend, worker, nginx и GitHub Actions.
- [ ] `Bitrix24` webhook URL не логируется.
- [ ] `MAX` token не логируется.

Проверки:

```bash
git status --short
git ls-files .env .env.* || true
git grep -n "BITRIX24_WEBHOOK_URL" || true
```

## SSH And VPS Access

- [ ] SSH password login выключен.
- [ ] Root login выключен.
- [ ] Для деплоя используется пользователь `deploy`.
- [ ] `deploy` имеет доступ к Docker без использования root.

Проверки на VPS:

```bash
whoami
sudo sshd -T | grep -E "passwordauthentication|permitrootlogin|pubkeyauthentication"
id deploy
```

## Network Exposure

- [ ] Наружу опубликован только nginx.
- [ ] PostgreSQL не опубликован наружу.
- [ ] Redis не опубликован наружу.
- [ ] Known open ports проверены и имеют понятное назначение.
- [ ] `nginx` fallback корректный: `/` возвращает WebApp, API routes проксируются в backend, неизвестные API/служебные пути не раскрывают лишнюю информацию.

Проверки на VPS:

```bash
sudo ufw status
ss -tulpn
docker compose -f docker-compose.prod.yml ps
curl -I http://localhost/
curl -I http://localhost/api/health
```

## Runtime Configuration

- [ ] `DEBUG=false`.
- [ ] `AI_ENABLED=false`, если AI не используется в пилоте.
- [ ] `DEV_AUTH_ENABLED=false` в production, если dev auth явно не нужен.
- [ ] Внешние интеграции выключены по умолчанию.
- [ ] `BITRIX24_ENABLED=false`, если реальный Bitrix24 webhook не настроен.
- [ ] `MAX_SENDER_ENABLED=false`, если реальная отправка в MAX не включена.

Проверки на VPS:

```bash
cd /opt/max_secretary/app
grep -E "^(APP_ENV|DEBUG|AI_ENABLED|DEV_AUTH_ENABLED|BITRIX24_ENABLED|MAX_SENDER_ENABLED)=" .env
```

## Backup And Release Safety

- [ ] Backup PostgreSQL сделан перед обновлением.
- [ ] Backup-файл проверен и доступен для восстановления.
- [ ] Инструкция restore доступна оператору.
- [ ] Предыдущий release tag известен для rollback.

Проверки:

```bash
./scripts/ops/backup_postgres.sh
ls -lh backups/
git tag --list "v*"
```

## Final Gate

- [ ] `docker compose -f docker-compose.prod.yml config` проходит успешно.
- [ ] Все контейнеры `Up` или `healthy`.
- [ ] `/api/health` возвращает `ok`.
- [ ] WebApp routes открываются.
- [ ] Smoke-тесты release проходят без реальных MAX/Bitrix24 секретов.

Команды:

```bash
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/health
BASE_URL=http://localhost ./scripts/release/smoke_release_1_0.sh
```
