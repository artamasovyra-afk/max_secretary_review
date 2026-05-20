# Bitrix24 Connector Smoke Test

Документ описывает smoke-тест Bitrix24 Connector в disabled mode.

Тест не использует реальные Bitrix24 webhook URL, токены или доступ к Битрикс24. Ожидаемый режим для MVP без реального webhook:

```env
BITRIX24_ENABLED=false
```

Protected Bitrix24 endpoints используют dev auth headers. Если на production `DEV_AUTH_ENABLED=false`, скрипт корректно завершится со статусом `skipped_auth_disabled`: это означает, что защищенные endpoints закрыты для header auth.

## Запуск локально

```bash
BASE_URL=http://localhost scripts/smoke_test_bitrix24_connector.sh
```

## Запуск на VPS

На VPS запускать из корня проекта:

```bash
cd /opt/max_secretary/app
BASE_URL=http://localhost scripts/smoke_test_bitrix24_connector.sh
```

## Требования

На машине должны быть доступны:

- `curl`
- `jq`

Скрипт использует:

```bash
BASE_URL="${BASE_URL:-http://localhost}"
```

## Сценарий

1. Проверить `GET /api/health`.
2. Создать тестовую организацию.
3. Создать постановщика.
4. Создать исполнителя.
5. Создать `BitrixUserMapping` для исполнителя.
6. Создать чат.
7. Добавить участников чата.
8. Создать задачу.
9. Вызвать ручную синхронизацию:

```text
POST /api/integrations/bitrix24/tasks/{task_id}/sync
```

10. Проверить, что при `BITRIX24_ENABLED=false` ответ содержит:

```json
{
  "sync_status": "disabled"
}
```

11. Проверить статус синхронизации:

```text
GET /api/integrations/bitrix24/tasks/{task_id}/status
```

12. Ожидаемый статус:

```json
{
  "sync_status": "disabled"
}
```

## Ожидания

- Smoke-test не требует `BITRIX24_WEBHOOK_URL`.
- Smoke-test не выполняет реальные HTTP-запросы в Битрикс24.
- `disabled` является ожидаемым успешным результатом для окружения без реального webhook.
- `skipped_auth_disabled` является ожидаемым результатом для production, где dev header auth выключен.
- WebApp smoke-test дополнительно проверяет Bitrix24 status API через `GET /api/integrations/bitrix24/tasks/{task_id}/status` без реального Bitrix24.
- Скрипт выводит summary с созданными ID.

## Ограничения

- Тест создает persistent smoke-данные в базе.
- Реальная отправка в Битрикс24 проверяется отдельным тестом после настройки webhook и включения `BITRIX24_ENABLED=true`.
