# Tech Stack

This document describes the current `max_secretary v1.0.x` technology stack.

## Backend

- Python 3.12.
- FastAPI.
- Pydantic and `pydantic-settings`.
- SQLAlchemy 2.x async.
- Alembic.
- `asyncpg`.
- `httpx` for integration clients.
- APScheduler for reminder scheduling in the worker container.
- Pytest and Ruff for tests/lint.

The FastAPI application starts as:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Database

PostgreSQL is the only database for dev, production and Docker environments.

The application requires `DATABASE_URL` in this format:

```text
postgresql+asyncpg://USER:PASSWORD@postgres:5432/DB_NAME
```

SQLite is not part of the dev, production or Docker runtime stack and must not be used as an application fallback.

## Cache And Queue Foundation

Redis is included in production/offline compose as the cache/queue foundation.

Current use is intentionally lightweight. Redis is available for future queue, lock and scheduling improvements, while reminders currently run through the worker scheduler.

## Worker

The worker container uses the backend image and runs:

```bash
python -m app.workers.jobs
```

It is responsible for reminder scheduler jobs and exposes a heartbeat-based healthcheck.

## WebApp

- React.
- TypeScript.
- Vite.
- Ant Design.
- React Router.
- API client wrappers under `webapp/src/api/`.
- Dev AuthContext preparation for future MAX WebApp auth.

The production WebApp image uses a multi-stage Dockerfile:

1. Node build stage with `npm ci` and `npm run build`.
2. nginx serve stage for static files and SPA fallback.

## Reverse Proxy

Production `nginx` is the public entry point.

Routing:

- `/api/*` -> backend.
- `/docs` -> backend.
- `/openapi.json` -> backend.
- frontend routes -> WebApp.

## Deployment

Production deployment:

- Docker Compose.
- `docker-compose.prod.yml`.
- GitHub Actions manual SSH deploy workflow.
- VPS user: `deploy`.

Offline deployment:

- `docker-compose.offline.yml`.
- prebuilt Docker images.
- Python wheelhouse.
- release manifest and SHA256 checksums.

## External Integrations

MAX Bot:

- webhook adapter;
- command parser;
- normalized event layer;
- switchable sender;
- real sender disabled unless configured.

Bitrix24:

- settings and models;
- user mapping API;
- REST client adapter;
- task mapper;
- manual sync service;
- status tracking through `BitrixTaskLink`;
- no automatic triggers in `v1.0.0`.

AI:

- configuration switches exist;
- `AI_ENABLED=false` by default;
- no AI workflow is enabled in the pilot baseline.

## CI/CD

Current workflows:

- Backend CI: Ruff, Pytest, FastAPI import check.
- Deploy to VPS: manual `workflow_dispatch`, SSH deployment as `deploy`.

Known hardening gap: WebApp build, Docker Compose config and offline compose config should be added to CI/release gate before a stricter production release.
