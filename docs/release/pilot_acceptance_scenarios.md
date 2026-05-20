# Pilot Acceptance Scenarios

Документ описывает приемочные сценарии для пилотной версии `max_secretary`.

## 1. Создать Организацию, Чат, Пользователей

Цель: проверить базовую подготовку рабочей области.

Шаги:

1. Создать organization через API.
2. Создать chat внутри organization.
3. Создать пользователей: постановщик, исполнитель 1, исполнитель 2, наблюдатель.
4. Добавить пользователей в chat members.

Ожидаемый результат:

- organization создана;
- chat создан и связан с organization;
- пользователи созданы;
- участники добавлены в чат с нужными ролями.

## 2. Создать Задачу С Двумя Исполнителями И Наблюдателем

Цель: проверить создание задачи с несколькими участниками.

Шаги:

1. Отправить `POST /api/tasks`.
2. Указать `organization_id`, `chat_id`, `created_by_user_id`.
3. Передать двух пользователей в `assignee_ids`.
4. Передать наблюдателя в `observer_ids`.

Ожидаемый результат:

- задача создана со статусом `new`;
- созданы две связи `TaskAssignee`;
- создана связь `TaskObserver`;
- создана запись status history.

## 3. Исполнитель Оставляет Комментарий

Цель: проверить comments workflow.

Шаги:

1. От имени исполнителя вызвать `POST /api/tasks/{task_id}/comments`.
2. Передать `user_id` и непустой `text`.
3. Получить список комментариев задачи.

Ожидаемый результат:

- комментарий создан;
- комментарий связан с задачей;
- комментарий отображается в карточке задачи.

## 4. Исполнитель Добавляет File Metadata

Цель: проверить добавление metadata файла без фактической загрузки.

Шаги:

1. От имени исполнителя вызвать `POST /api/tasks/{task_id}/files`.
2. Передать `uploaded_by_user_id` и `file_name`.
3. При необходимости передать `file_url`, `file_storage_key`, `mime_type`, `size_bytes`.
4. Получить список файлов задачи.

Ожидаемый результат:

- file metadata создана;
- файл связан с задачей;
- фактическая загрузка файла не требуется.

## 5. Исполнитель Отправляет Ответ

Цель: проверить response workflow исполнителя.

Шаги:

1. От имени исполнителя вызвать `POST /api/tasks/{task_id}/responses`.
2. Передать `user_id` исполнителя и текст ответа.
3. Получить карточку задачи.

Ожидаемый результат:

- создан `TaskResponse` со статусом `submitted`;
- `TaskAssignee.status` изменен на `responded`;
- для `any_assignee_response` задача переходит в `waiting_acceptance`.

## 6. Постановщик Принимает Результат

Цель: проверить acceptance workflow.

Шаги:

1. От имени постановщика вызвать `POST /api/tasks/{task_id}/responses/{response_id}/accept`.
2. Передать `accepted_by_user_id`.
3. Получить карточку задачи.

Ожидаемый результат:

- создана запись `TaskAcceptance` с decision `accepted`;
- `TaskResponse.status` изменен на `accepted`;
- задача переведена в `done`;
- заполнено `completed_at`;
- создана запись status history.

## 7. Задача Переходит В done

Цель: проверить финальное состояние успешной задачи.

Шаги:

1. Получить задачу через `GET /api/tasks/{task_id}` после приемки.
2. Проверить `status`.
3. Проверить status history.

Ожидаемый результат:

- `status=done`;
- `completed_at` не пустой;
- status history содержит переход в `done`.

## 8. Задача Появляется В Dashboard

Цель: проверить единый свод задач пользователя.

Шаги:

1. Открыть WebApp Dashboard или вызвать `GET /api/tasks/inbox/summary`.
2. Передать пользователя через dev auth context или query `user_id` для MVP.
3. Проверить блоки `my_tasks`, `created_by_me`, `observed_by_me`.

Ожидаемый результат:

- задача отображается в соответствующих блоках;
- счетчики блоков корректны;
- ссылка на карточку задачи открывается.

## 9. Просроченная Задача Определяется Как overdue

Цель: проверить overdue detection.

Шаги:

1. Создать задачу с `deadline_at` в прошлом.
2. Запустить reminder job `mark_overdue_tasks` или smoke test reminders.
3. Получить карточку задачи.

Ожидаемый результат:

- задача получает статус `overdue`;
- задачи в `done` или `cancelled` не переводятся в overdue.

## 10. Reminder Worker Не Падает

Цель: проверить стабильность worker container.

Шаги:

1. Запустить production compose.
2. Проверить `docker compose -f docker-compose.prod.yml ps`.
3. Посмотреть логи worker.

Ожидаемый результат:

- worker container находится в состоянии `Up`;
- scheduler стартует, если reminders enabled;
- при disabled mode worker корректно пишет, что reminders disabled;
- в логах нет crash loop.

## 11. WebApp Task Details Открывается

Цель: проверить карточку задачи во frontend.

Шаги:

1. Открыть `/tasks/{task_id}`.
2. Передать `user_id` через dev auth query, если нужны действия.
3. Проверить основные блоки карточки.

Ожидаемый результат:

- страница возвращает HTTP 200;
- отображаются title, status, assignees, observers, comments, files, responses и status history;
- действия доступны при наличии auth context.

## 12. Bitrix24 Sync Status Отображается

Цель: проверить WebApp-индикатор статуса Bitrix24 sync.

Шаги:

1. Открыть WebApp task details.
2. Найти блок Bitrix24 sync.
3. Проверить текущий статус.

Ожидаемый результат:

- отображается один из статусов: `disabled`, `pending`, `synced`, `error`;
- ошибки показываются безопасно, без webhook URL или secret values.

## 13. При BITRIX24_ENABLED=false Ручная Синхронизация Возвращает disabled

Цель: проверить безопасный disabled mode интеграции.

Шаги:

1. Убедиться, что `BITRIX24_ENABLED=false`.
2. Вызвать `POST /api/integrations/bitrix24/tasks/{task_id}/sync`.
3. Получить `GET /api/integrations/bitrix24/tasks/{task_id}/status`.

Ожидаемый результат:

- sync endpoint возвращает `sync_status=disabled`;
- status endpoint возвращает `disabled`;
- реальные HTTP-запросы в Bitrix24 не выполняются;
- основной task workflow не падает.

## 14. RBAC Запрещает Неавторизованное Действие

Цель: проверить базовую защиту protected endpoints.

Шаги:

1. Вызвать protected Bitrix24 endpoint без auth headers.
2. Вызвать task sync от пользователя, который не является постановщиком и не имеет роли `manager`, `chat_admin` или `super_admin`.
3. Повторить запрос с корректными headers и ролью.

Ожидаемый результат:

- без auth context API возвращает `401`;
- без нужных прав API возвращает `403`;
- с корректными правами действие выполняется.

## 15. Offline Compose Config Проходит Проверку

Цель: проверить готовность закрытого контура.

Шаги:

1. Выполнить:

```bash
docker compose -f docker-compose.offline.yml config
```

2. Проверить, что в offline compose нет `build`.
3. Проверить, что используются заранее загруженные images.

Ожидаемый результат:

- compose config проходит без ошибок;
- backend и webapp используют `image`;
- postgres и redis не публикуют порты наружу;
- наружу опубликован только nginx на 80 порту.
