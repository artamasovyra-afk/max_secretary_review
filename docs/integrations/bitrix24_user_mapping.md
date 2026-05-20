# Bitrix24 User Mapping

User mapping нужен, чтобы связать локального пользователя `max_secretary` с пользователем Битрикс24. Без такого сопоставления backend не может надежно назначать ответственных, постановщиков, соисполнителей и наблюдателей во внешней задаче.

## Связь пользователей

Локальный `User.id` связывается с внешним `bitrix_user_id`.

`bitrix_user_id` хранится строкой, чтобы не зависеть от конкретного типа внешнего ID в Битрикс24.

Внутри одной организации для одного локального пользователя допускается только один активный mapping. Старые или ошибочные записи можно отключить через `is_active=false`.

## match_source

`match_source` показывает, как был найден или создан mapping:

- `manual` — mapping создан вручную оператором или администратором.
- `email` — пользователь сопоставлен по email.
- `phone` — пользователь сопоставлен по телефону.
- `import` — mapping получен из будущего импорта пользователей.

## MVP

На MVP mapping создается вручную через API:

```text
POST /api/integrations/bitrix24/user-mappings
GET /api/integrations/bitrix24/user-mappings
GET /api/integrations/bitrix24/user-mappings/{mapping_id}
PATCH /api/integrations/bitrix24/user-mappings/{mapping_id}
DELETE /api/integrations/bitrix24/user-mappings/{mapping_id}
```

`DELETE` не удаляет запись физически, а переводит `is_active=false`.

Автоматический импорт пользователей из Битрикс24 будет добавлен позже.
