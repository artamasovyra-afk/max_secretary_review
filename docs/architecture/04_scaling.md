# Scaling And Deployment

This document describes the current scaling and deployment model for `max_secretary v1.0.x`.

## Current Deployment Shape

The pilot deployment is a single-VPS Docker Compose stack:

```text
nginx -> webapp
nginx -> backend -> postgres
                 -> redis
worker -> postgres
worker -> redis
```

Services:

- `nginx` is the only public entry point.
- `backend` serves FastAPI.
- `webapp` serves static React assets.
- `worker` runs reminder scheduler jobs.
- `postgres` stores application data.
- `redis` is available as cache/queue foundation.

This shape is intentionally simple for the pilot.

## Production Compose

Production compose file:

```text
docker-compose.prod.yml
```

Characteristics:

- builds backend image from `./backend`;
- builds webapp image from `./webapp`;
- uses `postgres:16`;
- uses `redis:7`;
- uses `nginx:stable`;
- publishes only `nginx:80`;
- keeps backend, worker, webapp, PostgreSQL and Redis internal to the Docker network;
- includes healthchecks for all services on current `main`.

Core commands:

```bash
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## Offline Compose

Offline compose file:

```text
docker-compose.offline.yml
```

Characteristics:

- does not use `build:`;
- runs from preloaded Docker images;
- is designed for closed-contour deployment;
- uses `.env` on the target server;
- publishes only `nginx:80`.

Note: the current offline compose still uses `0.9.0` image tags and should be synchronized with the intended release version before a strict `1.0.x` offline rollout.

## Healthchecks

Current production healthchecks:

- PostgreSQL: `pg_isready`.
- Redis: `redis-cli ping`.
- Backend: `curl` against `/api/health`.
- Worker: heartbeat file checked by `python -m app.workers.jobs --healthcheck`.
- WebApp: nginx pid/process/config check.
- Nginx: nginx pid/process/config check.

Healthcheck status is visible with:

```bash
docker compose -f docker-compose.prod.yml ps
```

## Worker Scaling

The worker currently runs as one scheduler process.

Important constraints:

- scheduler must run in the worker container, not in each Uvicorn worker;
- duplicate scheduler instances can produce duplicate reminders;
- horizontal worker scaling needs a locking/leader-election strategy before multiple replicas are enabled.

Future scaling options:

- Redis-based distributed lock for scheduler jobs;
- Celery/Celery Beat or another queue scheduler;
- separate queues for reminders, integrations and maintenance jobs.

## Backend Scaling

The backend is stateless with respect to HTTP requests, except for database and integration side effects.

Potential scaling path:

1. Increase Uvicorn worker/process count inside backend container if needed.
2. Split API and worker responsibilities strictly; do not run scheduler in API workers.
3. Add a load balancer or external reverse proxy if multiple backend containers are used.
4. Use database pool sizing and PostgreSQL monitoring before increasing concurrency aggressively.

## Database Scaling

Current PostgreSQL deployment is a single container with a named volume.

Pilot assumptions:

- one primary PostgreSQL instance;
- backups through `scripts/ops/backup_postgres.sh`;
- restore tested in a separate database/environment, not over production;
- no read replicas in pilot scope.

Future options:

- managed PostgreSQL;
- PITR backups;
- replica for reporting;
- migration window and rollback automation.

## WebApp Scaling

WebApp is static content served by nginx. It can be scaled by:

- rebuilding static image;
- serving through a CDN or internal artifact server if allowed;
- placing additional reverse proxy/cache in front of nginx.

For closed contours, WebApp assets are part of the Docker image and must not depend on external CDN.

## Integration Scaling

MAX and Bitrix24 integrations are intentionally conservative:

- MAX sender can run in logging-only mode or real API mode.
- Bitrix24 sync is manual in MVP.
- Automatic Bitrix24 triggers are disabled to avoid duplicate external tasks.
- Integration errors must not break the core task workflow.

Before automatic integration triggers are enabled, add idempotency, retry policy, rate-limit handling and operational dashboards.

## Release Gate

Minimum production checks:

- backend tests and Ruff;
- WebApp build;
- `docker compose -f docker-compose.prod.yml config`;
- migrations;
- `/api/health`;
- WebApp routes;
- MVP smoke;
- reminders smoke;
- Bitrix24 disabled smoke;
- backup before upgrade.

See [Production deployment checklist](../release/production_deployment_checklist.md).
