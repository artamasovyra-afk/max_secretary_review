# Roles And Permissions

Документ описывает актуальную модель ролей и прав `max_secretary v1.0.0`.

RBAC в `v1.0.0` является подготовительным слоем: policy уже реализована в backend и используется для защищенных Bitrix24 endpoints, но не все product endpoints полностью переведены на обязательную авторизацию.

## Роли

### `member`

Базовый участник чата.

Может работать со своими задачами и доступными задачами чата, если политика чата это разрешает. Может отправлять ответы по задачам, где он исполнитель, оставлять комментарии и добавлять file metadata к доступным задачам.

### `manager`

Пользователь, который управляет рабочими задачами внутри доступного ему scope.

В текущей policy `manager`:

- может видеть задачи чата или организации в своем scope;
- может создавать задачи в доступном чате;
- может обновлять задачи в доступном scope;
- может запускать ручную Bitrix24 sync по доступным задачам;
- не получает автоматическое право принять или отклонить результат чужой задачи, если он не постановщик.

### `chat_admin`

Администратор чата или рабочей области в рамках организации.

В текущей policy `chat_admin` наследует manager-level возможности и дополнительно может управлять Bitrix24 user mapping в рамках своей организации. Также целевая модель предполагает управление участниками и настройками чата.

### `super_admin`

Глобальный администратор.

Имеет полный доступ ко всем организациям, чатам, задачам и интеграциям. В policy `super_admin` определяется через `AuthContext.is_super_admin=true` или роль `super_admin` в `X-Roles`.

## Permission Registry

Backend registry содержит следующие permissions:

### Tasks

- `task.view` — просмотр задачи.
- `task.create` — создание задачи.
- `task.update` — изменение задачи.
- `task.cancel` — отмена задачи.
- `task.assign` — управление исполнителями.
- `task.comment` — добавление комментариев.
- `task.file.add` — добавление file metadata.
- `task.response.submit` — отправка ответа исполнителя.
- `task.accept` — приемка результата.
- `task.reject` — отклонение результата.

### Chats

- `chat.members.manage` — управление участниками чата.
- `chat.settings.manage` — управление настройками чата.

### Bitrix24 And Integrations

- `bitrix.mapping.manage` — управление сопоставлением локальных пользователей и Bitrix24 users.
- `bitrix.sync.run` — запуск ручной синхронизации задачи с Битрикс24.
- `integration.settings.manage` — управление настройками интеграций.

## Основные Правила Policy

### Просмотр Задачи

Задачу может видеть:

- `super_admin`;
- постановщик задачи;
- исполнитель задачи;
- наблюдатель задачи;
- `manager` или `chat_admin` в совпадающем chat/organization scope;
- `member` в совпадающем scope, если настройки чата разрешают просмотр задач участниками.

### Создание Задачи

Создать задачу может:

- `super_admin`;
- `manager` или `chat_admin`, если текущий `AuthContext` совпадает с чатом или организацией.

### Обновление Задачи

Обновить задачу может:

- `super_admin`;
- постановщик задачи;
- `manager` или `chat_admin` в совпадающем scope.

### Ответ Исполнителя

Исполнитель может отправить ответ только по задаче, где он есть в списке `TaskAssignee`.

`super_admin` может пройти policy-проверку, но product flow все равно должен учитывать бизнес-правило: обычный ответ исполнителя должен принадлежать назначенному исполнителю.

### Приемка И Отклонение

Принять или отклонить результат может:

- постановщик задачи;
- `super_admin`.

Наблюдатель не может принять или отклонить результат только на основании статуса наблюдателя.

### Наблюдатель

Наблюдатель:

- может видеть задачу;
- не является исполнителем;
- не обязан отправлять ответ;
- не влияет на `completion_rule`;
- не принимает и не отклоняет результат без отдельной роли или права.

### Manager

`manager` видит задачи доступного чата или организации и может управлять рабочими задачами в своем scope.

В текущей policy `manager` может:

- просматривать задачи в scope;
- создавать задачи в scope;
- обновлять задачи в scope;
- запускать ручную Bitrix24 sync по доступным задачам.

Приемка/отклонение результата manager-ом чужой задачи не включена в текущую policy как override.

### Chat Admin

`chat_admin` может:

- выполнять manager-level действия в scope;
- управлять Bitrix24 user mapping в рамках организации;
- по целевой модели управлять участниками и настройками чата.

### Super Admin

`super_admin` имеет полный доступ ко всем policy actions.

## Bitrix24 Permissions

### Ручная Синхронизация

Запустить ручную Bitrix24 sync по задаче может:

- постановщик задачи;
- `manager` или `chat_admin` в совпадающем scope;
- `super_admin`.

Посторонний пользователь не должен запускать sync.

### Просмотр Sync Status

Статус синхронизации доступен пользователям, которые могут видеть задачу.

### Retry Failed Sync

Повтор failed sync доступен только:

- `chat_admin`;
- `super_admin`.

### User Mapping CRUD

Управление Bitrix24 user mapping доступно:

- `chat_admin` в рамках своей организации;
- `super_admin`.

`manager` не управляет mapping в текущей реализации, если не будет добавлена отдельная настройка.

## Dev Auth

Для подготовки WebApp auth и protected endpoints используется временный dev auth через HTTP headers.

Основные headers:

- `X-User-Id` — UUID текущего пользователя.
- `X-Organization-Id` — UUID текущей организации, если нужен scope.
- `X-Chat-Id` — UUID текущего чата, если нужен scope.
- `X-Roles` — роли через запятую, например `member,manager`.

`AuthContext` содержит:

- `user_id`;
- `organization_id`;
- `chat_id`;
- `roles`;
- `is_super_admin`.

## `DEV_AUTH_ENABLED`

В `APP_ENV=local` и `APP_ENV=test` dev auth headers разрешены.

В `APP_ENV=production` dev auth headers отключены по умолчанию:

```env
DEV_AUTH_ENABLED=false
```

Включение:

```env
DEV_AUTH_ENABLED=true
```

допустимо только как временный переходный режим и не является финальной production auth.

## Ограничения MVP

- Полноценная MAX WebApp auth еще не реализована.
- Dev auth через headers является временным механизмом.
- Query parameter `user_id` не должен использоваться как источник авторизации для новых protected endpoints.
- RBAC enforcement подключен не ко всем endpoint'ам.
- Manager/chat_admin override для приемки чужих задач не включен в текущую policy.
- Bitrix24 sync защищен RBAC, но автоматические sync triggers не реализованы.

## Связанные Документы

- [RBAC policy](../security/rbac_policy.md)
- [WebApp auth preparation](../security/webapp_auth_preparation.md)
- [Task lifecycle](task_lifecycle.md)
- [Bitrix24 integration](../integrations/bitrix24.md)
