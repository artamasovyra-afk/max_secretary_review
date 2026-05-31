# max_secretary

Бот-секретарь для MAX — инструмент фиксации и контроля поручений из рабочих чатов. `max_secretary` превращает переписку в задачи со сроками, несколькими исполнителями, наблюдателями, комментариями, file metadata, ответами исполнителей и приемкой результата постановщиком.

Текущая версия review-снимка: `1.1.0-rc.3`.

Этот репозиторий подготовлен для передачи заказчику на тестирование версии 1.1.x. Он содержит актуальный код backend/WebApp, инфраструктурные файлы, документацию и customer test plan. Production-секреты, `.env`, токены и deployment credentials в репозиторий не входят.

## Возможности

- Организации, пользователи, чаты и участники чатов.
- Задачи с несколькими исполнителями и наблюдателями.
- Комментарии и file metadata.
- Ответ исполнителя.
- Приемка или отклонение результата постановщиком.
- Единый свод задач пользователя из разных чатов.
- Напоминания и worker scheduler.
- MAX Bot webhook adapter и команды MVP.
- Bitrix24 вынесен из текущего тестового релиза и запланирован на версию 2.0.0.
- RBAC policy layer и подготовка WebApp auth context.
- MAX WebApp: задачи, action sheet, "Задача участникам чата", настройки и super-admin.
- Clean task/report wizard flows, приемка и отклонение отчетов с причиной.
- Opt-in deadline reminders для подключенных чатов.
- Production deployment через Docker Compose.
- Offline/closed contour delivery path.

## Customer Testing

Основной документ для проверки заказчиком:

- [Customer test plan v1.1](docs/product/customer_test_plan_v1.1.md)

Он описывает состав версии, исключения, роли, сценарии, критерии критичных багов и формат обратной связи.

## Архитектура

- `backend` — FastAPI backend, SQLAlchemy async, Alembic.
- `webapp` — React, TypeScript, Vite, Ant Design.
- `postgres` — основная БД проекта.
- `redis` — cache/queue foundation.
- `worker` — reminder scheduler и фоновые jobs.
- `nginx` — публичная точка входа, WebApp routing и API reverse proxy.

PostgreSQL является единственной production/dev/docker БД. `DATABASE_URL` должен использовать `postgresql+asyncpg://...`; SQLite не используется как application fallback.

## Быстрый Запуск Через Docker Compose

```bash
cp .env.example .env
nano .env
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
curl http://localhost/api/health
```

WebApp:

```bash
curl -I http://localhost/
curl -I http://localhost/tasks
curl -I http://localhost/dashboard
```

Подробности backend-разработки: [backend/README.md](backend/README.md).

## VPS Deployment

- [Create deploy user](docs/deployment/01_create_deploy_user.md)
- [SSH key access](docs/deployment/02_setup_ssh_key.md)
- [Install Docker](docs/deployment/03_install_docker.md)
- [Clone repository](docs/deployment/04_clone_repository.md)
- [Server `.env`](docs/deployment/05_server_env.md)
- [GitHub Secrets](docs/deployment/06_github_secrets.md)
- [GitHub Actions deploy](docs/deployment/07_first_github_actions_deploy.md)
- [Manual deploy](docs/deployment/08_manual_deploy.md)
- [VPS runtime tuning](docs/deployment/10_vps_runtime_tuning.md)

## Offline / Closed Contour

- [Offline delivery policy](docs/deployment/offline_delivery_policy.md)
- [Offline bundle build](docs/deployment/offline_bundle_build.md)
- [Offline Docker Compose](docs/deployment/offline_compose.md)
- [Offline Docker images](docs/deployment/offline_docker_images.md)
- [Offline install guide](docs/deployment/offline_install_guide.md)
- [Offline manifest and checksums](docs/deployment/offline_manifest_checksums.md)
- [Offline Python wheelhouse](docs/deployment/offline_python_wheelhouse.md)
- [Manual dependency update policy](docs/deployment/manual_dependency_update_policy.md)

## Backup / Restore

- [Backup and restore guide](docs/operations/backup_restore.md)
- [Operator guide](docs/operations/operator_guide.md)

Перед обновлением production версии нужно сделать backup PostgreSQL:

```bash
scripts/ops/backup_postgres.sh
gzip -t backups/max_secretary_YYYYMMDD_HHMMSS.sql.gz
```

Restore не выполняется поверх production БД для проверки backup. Для проверки используется отдельная test database или отдельное тестовое окружение.

## Smoke / Release Checks

Основной release smoke:

```bash
BASE_URL=http://localhost scripts/release/smoke_release_1_0.sh
```

Отдельные smoke scripts:

- `scripts/smoke_test_mvp.sh`
- `scripts/smoke_test_webapp.sh`
- `scripts/smoke_test_bot_webhook.sh`
- `scripts/smoke_test_reminders.sh`
- `scripts/smoke_test_bitrix24_connector.sh`
- `scripts/smoke_test_max_sender.sh`

Release artifacts and customer docs:

- [Customer test plan v1.1](docs/product/customer_test_plan_v1.1.md)
- [Pilot deployment report](docs/release/1.0.0_pilot_deployment_report.md)
- [Production deployment checklist](docs/release/production_deployment_checklist.md)
- [Security checklist](docs/release/security_checklist_1.0.0.md)
- [Release smoke procedure](docs/release/release_smoke.md)
- [v1.1 merge readiness report](docs/release/v1.1_merge_readiness_report.md)

## Ограничения Пилота

- `1.1.0-rc.3` — release candidate для customer testing, не full production certification.
- Bitrix24 sync, automatic Bitrix24 triggers, two-way sync и import переносятся в версию 2.0.0.
- File upload пока хранит только metadata.
- Observability stack не полный.
- Closed contour bundle требует отдельной инфраструктурной приемки.

Подробнее:

- [Customer test plan v1.1](docs/product/customer_test_plan_v1.1.md)
- [Pilot user guide](docs/product/pilot_user_guide.md)
- [WebApp mobile UX v1.1](docs/product/webapp_mobile_ux_v1.1.md)
- [Bitrix24 integration](docs/integrations/bitrix24.md)
- [MAX bot setup](docs/integrations/max_bot_setup.md)
