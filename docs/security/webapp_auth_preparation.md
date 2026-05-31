# WebApp Auth Preparation

Документ описывает подготовительный слой авторизации WebApp для max_secretary. Это MVP/dev режим и временный мост к будущей авторизации через MAX WebApp.

## Цель

WebApp должен получать пользователя один раз через единый `AuthContext`, а не прокидывать `user_id` вручную через каждый компонент. API client использует этот context для отправки backend headers, которые затем могут быть проверены RBAC policy layer.

## Текущий MVP/dev режим

Пока полноценная MAX WebApp auth не подключена, WebApp может читать dev auth из query parameters:

- `user_id` — UUID текущего пользователя.
- `organization_id` — UUID текущей организации, опционально.
- `chat_id` — UUID текущего чата, опционально.
- `roles` — список ролей через запятую, например `member,chat_admin`.

Пример:

```text
/tasks/00000000-0000-0000-0000-000000000000?user_id=11111111-1111-1111-1111-111111111111&organization_id=22222222-2222-2222-2222-222222222222&chat_id=33333333-3333-3333-3333-333333333333&roles=chat_admin
```

Если `user_id` передан через URL, WebApp показывает предупреждение:

```text
Dev auth mode: user_id передан через URL
```

## Frontend структура

Auth слой находится в:

- `webapp/src/auth/AuthContext.tsx`
- `webapp/src/auth/useAuth.ts`
- `webapp/src/auth/devAuth.ts`

`DashboardPage` и `TaskDetailsPage` используют `useAuth()` вместо прямого чтения `user_id` из URL.

## API headers

WebApp API client автоматически добавляет headers, если auth context содержит значения:

- `X-User-Id`
- `X-Organization-Id`
- `X-Chat-Id`
- `X-Roles`

Эти headers предназначены для backend dependency `get_auth_context()` и будущего RBAC enforcement.

## Production режим

В production dev header auth должен быть выключен по умолчанию:

```env
DEV_AUTH_ENABLED=false
```

Включать `DEV_AUTH_ENABLED=true` в production можно только временно на переходном этапе. Это не замена полноценной MAX WebApp auth.

## Будущая MAX WebApp auth

Следующий этап должен заменить query-based dev auth на проверенный источник идентичности MAX WebApp:

- получение signed init data от MAX WebApp;
- server-side validation подписи;
- сопоставление MAX user id с локальным `User`;
- выдача backend auth context без ручного `user_id` в URL;
- отказ от dev headers в production.

## Ограничения MVP

- `user_id` в query parameter допустим только для dev/MVP режима.
- Query parameters не являются надежным источником идентичности.
- Backend должен считать headers dev-only механизмом, пока не подключена настоящая WebApp auth.
- Новые protected endpoints не должны использовать query `user_id` как auth source.
