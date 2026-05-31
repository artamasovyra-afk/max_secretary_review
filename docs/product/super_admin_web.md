# Super-Admin Web

Документ описывает отдельный web-контур супер-администратора `Дьяка`.

Этот интерфейс не является MAX WebApp и не использует MAX `initData`.

## Назначение

URL:

- `/super-admin`

Задачи:

- подключать новые MAX-чаты к `Дьяку`;
- видеть статус подключения чатов;
- раскрывать участников чата;
- назначать и снимать роль `chat_admin` внутри `Дьяка`;
- хранить контрольный контур отдельно от мобильного рабочего WebApp.

MAX WebApp остается интерфейсом задач: `/tasks`, `/settings`, `/group-assignments`.

## Авторизация

Super-admin web использует отдельную login/password авторизацию:

- `SUPER_ADMIN_LOGIN`;
- `SUPER_ADMIN_PASSWORD`;
- `SUPER_ADMIN_SESSION_SECRET`;
- httpOnly secure cookie `max_secretary_super_admin` по умолчанию.

Пароль не хранится во frontend и не логируется. Если переменные не заданы, super-admin login возвращает безопасную ошибку конфигурации, а приложение продолжает запускаться.

## Статусы Чатов

Статусы:

- `pending_approval` — ожидает подключения;
- `active` — подключен;
- `rejected` — отклонен;
- `suspended` — отключен или приостановлен.

Существующие чаты мигрируются в `active`, чтобы не ломать текущий рабочий контур.

Новые групповые MAX-чаты создаются как `pending_approval`. Личные диалоги остаются `active`, чтобы не ломать self-task сценарии.

В неподключенном чате команды отвечают:

> Этот чат еще не подключен к Дьяку. Ожидается подтверждение супер-администратора.

## API

Все endpoints `/api/super-admin/*`, кроме login/logout, защищены отдельной super-admin session cookie.

- `POST /api/super-admin/login`;
- `GET /api/super-admin/session`;
- `POST /api/super-admin/logout`;
- `GET /api/super-admin/status`;
- `GET /api/super-admin/chats`;
- `GET /api/super-admin/chats/{chat_id}/members`;
- `POST /api/super-admin/chats/{chat_id}/sync-max-chat-info`;
- `POST /api/super-admin/chats/{chat_id}/sync-max-admins`;
- `PATCH /api/super-admin/chats/{chat_id}/display-title`;
- `PATCH /api/super-admin/chats/{chat_id}/settings`;
- `PATCH /api/super-admin/chats/{chat_id}/status`;
- `PATCH /api/super-admin/chats/{chat_id}/members/{user_id}/role`.

Через role endpoint можно назначать только `member` и `chat_admin`. Роль `super_admin` этим endpoint не выдается.

Если активный чат остается без последнего `chat_admin`, backend требует явного подтверждения операции.

`GET /api/super-admin/chats` поддерживает безопасный status filter:

- `status=pending_approval`;
- `status=active`;
- `status=rejected`;
- `status=suspended`;
- legacy alias `status=pending` maps to `pending_approval`.

Фильтр возвращает только агрегаты и display-поля супер-админки; raw MAX ids не входят в response.

Webhook MAX не всегда передает надежное название чата при первом событии подключения. Поэтому backend использует два fallback-механизма:

- при создании нового group/max_chat без нормального title identity resolver пробует read-only lookup через MAX API `get_chat_info`;
- в super-admin UI есть ручное действие `Обновить из MAX`, которое вызывает `POST /api/super-admin/chats/{chat_id}/sync-max-chat-info` только для выбранного чата.

Если MAX API не вернул название или недоступен, super-admin задает alias через `PATCH /api/super-admin/chats/{chat_id}/display-title`. Alias хранится в `Chat.settings.display_title`, используется только внутри `Дьяка` и не меняет название в MAX.

## UI

Страница `/super-admin` показывает:

- header `Дьяк · Супер-админ`;
- logout;
- поиск по названию чата;
- фильтры `Все`, `Ожидают подключения`, `Подключены`, `Отклонены`, `Отключены`;
- карточки чатов со статусом, типом, количеством участников, количеством админов `Дьяка` и справочным числом админов MAX, если оно известно.

При смене status-фильтра UI сбрасывает поисковую строку и запрашивает `/api/super-admin/chats?status=...`, чтобы новый `pending_approval` чат не скрывался старым локальным поиском. SPA routes отдаются без cache storage для `index.html`, чтобы браузер быстрее получал свежий bundle после deploy.

Для pending-чата с fallback-названием `Чат без названия` UI показывает предупреждение, поле `Название чата в Дьяке`, кнопку `Сохранить название` и кнопку `Обновить из MAX`. Перед `Подключить` UI предупреждает, если название все еще не задано.

При раскрытии чата показываются участники:

- имя;
- роль в `Дьяке`;
- справочная отметка `Админ в MAX`: `Да`, `Нет`, `Не проверено`;
- чекбокс `Админ чата в Дьяке`.

Изменение чекбокса сразу вызывает API. В одном чате может быть несколько `chat_admin`.

Кнопка `Обновить роли MAX` запускает ручную проверку администраторов MAX только для выбранного чата. После успешной проверки список участников обновляется, а отметка `Админ в MAX` показывает сохраненный snapshot.

## Дедлайн-Уведомления

Дедлайн-уведомления включаются отдельно для каждого чата супер-администратором.

- Настройка хранится в `Chat.settings.deadline_reminders_enabled`.
- Значение по умолчанию: `false`; existing chats не включаются автоматически.
- В карточке active-чата есть переключатель `Дедлайн-уведомления`: `включены` / `выключены`.
- Для `pending_approval`, `rejected` и `suspended` чатов переключатель отключен с подсказкой `Доступно после подключения чата.`
- API: `PATCH /api/super-admin/chats/{chat_id}/settings` с payload `{ "deadline_reminders_enabled": true }`.
- На первом этапе менять настройку может только `super_admin`.

Эта настройка не заменяет production env gates. Scheduler отправляет `task_due_in_1h` и `task_overdue` только если включены global flags и конкретный чат opt-in.

Production deploy check on 2026-05-31 confirmed this flow on one active test chat: defaults were disabled for all active chats, super-admin enabled exactly one chat, scheduler sent one allowlisted overdue notification for task `#61`, and global flags were returned to safe values after the test.

Production recheck on 2026-05-31 kept the same opt-in chat `Тест ДЬЯК` enabled, used allowlist `73`, sent one scheduler `task_overdue` notification for task `#73`, prevented a duplicate after another scheduler interval, skipped other overdue candidates by allowlist, and returned global flags to safe values with an empty allowlist.

## MAX Admin Marker

Признак администратора MAX является справочным. Он не выдает прав в `Дьяке` автоматически.

Авторитетная роль для внутренних разрешений:

- `ChatMember.role = member`;
- `ChatMember.role = chat_admin`;
- системный `super_admin`.

Синхронизация MAX-ролей запускается вручную супер-администратором через `POST /api/super-admin/chats/{chat_id}/sync-max-admins`. Endpoint проверяет только один выбранный чат, сохраняет snapshot в настройках чата и возвращает только безопасные счетчики: сколько участников проверено, сколько MAX-админов найдено, сколько сопоставлено с участниками и сколько осталось без MAX id.

Значение `Не проверено` означает, что snapshot еще не получен или у участника нет MAX id для сопоставления.

## Безопасность

- Super-admin web отделен от MAX WebApp.
- MAX `initData` не принимается как super-admin auth.
- UI не показывает raw `user_id`, `chat_id`, `max_user_id`, `max_chat_id`.
- Изменения статуса чата и роли участника пишутся в audit log.
- В логах используются только masked ids.
- Member и chat_admin без super-admin cookie не получают доступ к API `/api/super-admin/*`.

## Later

- Экран управления участниками для `chat_admin` внутри обычного WebApp.
- Более богатый audit UI для истории подключений и смен ролей.

## Deploy Check 2026-05-28

Super-admin web deployed to VPS at commit `12a8c36`.

Confirmed:

- `/super-admin` frontend route is available.
- `/api/super-admin/chats` is blocked without super-admin cookie.
- login API succeeds with production credentials without printing secret values.
- authenticated chat list returns deployed chat records.
- participant read-only API returns role and MAX-admin marker fields.
- existing chats are migrated to `active`.
- Alembic current/head is `f9a0b1c2d3e4`.

Skipped intentionally:

- production role checkbox mutation, to avoid changing live chat roles without a separate approval.
- live creation of a new MAX chat, to avoid real MAX actions during deploy validation.

## Login Copy-Paste Behavior

The login form and backend ignore leading/trailing whitespace around submitted super-admin login and password.

This is intended only to make `.env` copy-paste safer. Password characters inside the value remain significant.

## Pending Title Sync Deploy Check 2026-05-29

Commit `d2caff2` was deployed and validated after recovering from a network interruption.

Confirmed:

- `/super-admin` route is available.
- Backend, worker, webapp, nginx, postgres, and redis are healthy.
- Alembic current/head is `f9a0b1c2d3e4`.
- The selected pending chat stayed `pending_approval`.
- Before sync, the chat displayed fallback title `Чат без названия`.
- One controlled read-only `sync-max-chat-info` call updated the display title to `Тест ДЬЯК`.
- The title source after sync is `real`.
- Manual alias was not needed.
- Approve/reject was not performed.
- Release smoke passed.

No raw chat ids, MAX ids, cookies, tokens, secrets, raw payloads, or raw MAX API responses were documented.
