# Backup And Restore

Документ описывает backup и restore PostgreSQL для `max_secretary`.

## Общие Правила

- Backup выполняется через PostgreSQL container.
- Пароли не хранятся в скриптах.
- Параметры подключения берутся из `.env` и окружения container.
- Backup-файлы сохраняются в `backups/`.
- `backups/` не коммитится в git.
- Restore перезаписывает данные в целевой базе и требует явного подтверждения.

## Создать Backup

Из корня проекта на VPS:

```bash
scripts/ops/backup_postgres.sh
```

По умолчанию используется:

```text
docker-compose.prod.yml
```

Если нужно использовать другой compose file:

```bash
COMPOSE_FILE=docker-compose.offline.yml scripts/ops/backup_postgres.sh
```

Файл будет создан в:

```text
backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

## Проверить Backup

Проверить, что файл существует и не пустой:

```bash
ls -lh backups/
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

Посмотреть начало SQL dump без распаковки на диск:

```bash
gunzip -c backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz | head
```

## Проверить Restore Без Риска Для Production

Не выполняйте restore поверх production database для проверки backup. Для restore-test используйте отдельную временную test database или отдельный PostgreSQL container.

Пример безопасной проверки во временной database внутри production PostgreSQL container:

```bash
cd /opt/max_secretary/app

BACKUP_FILE="backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz"
TEST_DB="restore_test_$(date +%Y%m%d_%H%M%S)"

gzip -t "$BACKUP_FILE"

docker compose -f docker-compose.prod.yml exec -T postgres \
  createdb -U max_secretary "$TEST_DB"

gunzip -c "$BACKUP_FILE" | docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U max_secretary -d "$TEST_DB"

docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U max_secretary -d "$TEST_DB" \
  -c "\dt"

docker compose -f docker-compose.prod.yml exec -T postgres \
  dropdb -U max_secretary "$TEST_DB"
```

Минимально проверить наличие таблиц:

- `organizations`
- `users`
- `chats`
- `tasks`
- `task_assignees`
- `bitrix_user_mappings`
- `bitrix_task_links`

### Restore-test после релиза 1.0.0

После обновления VPS до `v1.0.0` выполнена проверка backup:

- backup file: `backups/max_secretary_20260519_190707.sql.gz`
- gzip integrity check: passed
- restore target: temporary database `restore_test_20260519_191149`
- restore result: passed
- restored table count: `18`
- required tables restored: `organizations`, `users`, `chats`, `tasks`, `task_assignees`, `bitrix_user_mappings`, `bitrix_task_links`
- production database control before restore-test: `18` tables, `29` tasks
- production database control after restore-test: `18` tables, `29` tasks
- temporary restore database: dropped after verification

## Восстановить Backup

Restore выполняется через `psql` внутри `postgres` container:

```bash
scripts/ops/restore_postgres.sh backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

Скрипт попросит подтверждение:

```text
Type RESTORE to continue:
```

Для offline compose:

```bash
COMPOSE_FILE=docker-compose.offline.yml scripts/ops/restore_postgres.sh backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

## Хранение Backup

Рекомендации:

- хранить backup вне git;
- ограничить доступ к backup-файлам;
- регулярно переносить backup в защищенное хранилище;
- проверять восстановление на тестовом стенде;
- хранить несколько последних backup перед обновлениями;
- удалять старые backup по внутреннему регламенту.

## Перед Обновлением Версии

Перед production update:

1. Проверить текущий commit и версию.
2. Сделать backup:

```bash
scripts/ops/backup_postgres.sh
```

3. Проверить backup:

```bash
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

4. Выполнить deploy/update.
5. Применить миграции.
6. Проверить health и smoke tests.

## Troubleshooting

### postgres container is not running

Проверить:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 postgres
```

### permission denied docker

Пользователь должен иметь право выполнять Docker commands. После добавления в группу `docker` нужно открыть новую SSH-сессию.

### backup file is empty

Проверить логи postgres и переменные `POSTGRES_USER`, `POSTGRES_DB` внутри container:

```bash
docker compose -f docker-compose.prod.yml exec postgres env | grep POSTGRES
```

### restore fails

Проверить целостность gzip:

```bash
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

Запустить restore повторно только после понимания причины ошибки.
