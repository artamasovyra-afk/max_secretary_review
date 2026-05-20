# Architecture Overview

`max_secretary` is a modular monolith for turning working chat messages into controlled tasks. The system combines a FastAPI backend, PostgreSQL, Redis, a reminder worker, a React WebApp, nginx, MAX Bot integration adapters and a manual Bitrix24 connector.

The current baseline is `v1.0.0` pilot stable. It is suitable for pilot operation, not full production certification.

## Runtime Components

Production deployment uses Docker Compose and contains six services:

- `backend` — FastAPI application, API routes, domain services, SQLAlchemy async and Alembic.
- `worker` — background process for reminders scheduler and periodic jobs.
- `webapp` — React/Vite WebApp served by nginx inside the webapp container.
- `postgres` — primary relational database.
- `redis` — cache/queue foundation for current and future background processing.
- `nginx` — public entry point, reverse proxy for API/OpenAPI and WebApp routing.

Only `nginx` publishes port `80` externally. PostgreSQL, Redis, backend, worker and webapp stay inside the Docker network.

## Backend Structure

The backend is organized as a modular monolith:

```text
backend/app/
  api/
  core/
  db/
  modules/
    auth/
    bot/
    chats/
    integrations/
    notifications/
    organizations/
    reminders/
    tasks/
    users/
  workers/
```

Main module boundaries:

- `api/` wires FastAPI routers and dependencies.
- `core/` contains settings and shared application configuration.
- `db/` owns SQLAlchemy engine/session/base metadata.
- `modules/tasks/` owns task workflow, models, schemas, repositories and services.
- `modules/reminders/` owns reminder rules, selection logic and scheduler jobs.
- `modules/bot/` owns MAX command parsing and webhook command dispatch.
- `modules/integrations/bitrix24/` owns Bitrix24 settings, models, mapper, REST client and manual sync service.
- `modules/auth/` owns policy primitives and temporary auth context preparation.

Business logic stays in service/repository layers rather than in router functions where practical.

## Data Ownership

PostgreSQL is the only dev, production and Docker runtime database. The application requires `DATABASE_URL` in `postgresql+asyncpg://...` format and must not silently fall back to SQLite.

Alembic migrations live in `backend/alembic/` and are included in the backend Docker image. Migrations are applied from inside the backend container:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

See [Data Model](02_data_model.md) for entity groups.

## Request Flow

Typical WebApp/API flow:

1. Browser opens WebApp through public `nginx`.
2. WebApp calls `/api/*`.
3. `nginx` proxies `/api/*`, `/docs` and `/openapi.json` to `backend:8000`.
4. Backend executes service logic and reads/writes PostgreSQL.
5. Reminder worker independently scans due tasks and logs notification payloads through `MaxSender` when real sending is disabled.

Frontend routes such as `/`, `/tasks`, `/dashboard` and `/tasks/{id}` are routed by `nginx` to `webapp:80` for SPA fallback.

## Integrations

MAX integration is adapter-based:

- webhook endpoint: `POST /api/bot/max/webhook`;
- normalized bot event layer;
- command parser for MVP commands;
- switchable `MaxSender`, disabled/logging by default unless configured.

Bitrix24 integration is manual in `v1.0.0`:

- user mappings are managed through API;
- local tasks can be manually synced to Bitrix24;
- sync status is tracked through `BitrixTaskLink`;
- WebApp shows Bitrix24 status only in Task Details.

Automatic Bitrix24 triggers, two-way sync and Bitrix24 import are not part of the pilot baseline.

## Background Processing

The `worker` service runs reminder jobs and scheduler logic. It starts only as a separate Docker Compose service, not inside Uvicorn workers.

Current worker behavior:

- logs `worker started`;
- logs `reminders enabled` or `reminders disabled`;
- supports graceful shutdown on `SIGTERM`/`SIGINT`;
- writes a lightweight heartbeat file;
- exposes healthcheck through `python -m app.workers.jobs --healthcheck`.

## Deployment Modes

Supported deployment modes:

- Production VPS via `docker-compose.prod.yml`.
- Manual or GitHub Actions SSH deployment.
- Offline/closed-contour deployment via `docker-compose.offline.yml` and `vendor/` bundle.

Production compose builds backend and webapp images from source. Offline compose uses preloaded images and does not use `build:`.

## Security Boundary

Secrets are not stored in git. Runtime secrets live in `.env` on the server or in GitHub Secrets for deployment.

Important controls:

- `.env`, SSH key files, tokens and webhook URLs must not be committed.
- `DEV_AUTH_ENABLED=false` is expected in production unless explicitly approved for a temporary transition.
- Bitrix24 and MAX real senders are disabled by default unless configured.
- PostgreSQL and Redis are not exposed outside Docker network.
- RBAC policy exists and protects Bitrix24 sync/mapping endpoints; full MAX WebApp auth is still future work.

## Related Documents

- [Tech Stack](01_tech_stack.md)
- [Data Model](02_data_model.md)
- [API Overview](03_api.md)
- [Scaling](04_scaling.md)
- [Security](05_security.md)
- [Operator Guide](../operations/operator_guide.md)
- [Offline Deployment](../deployment/06_offline_deployment.md)
