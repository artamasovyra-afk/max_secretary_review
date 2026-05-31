# max_secretary backend

FastAPI backend for `max_secretary`: MVP core for organizations, users, chats, chat members and task lifecycle management.

## Local Run

Run commands from the `backend` directory.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://max_secretary:CHANGE_ME@localhost:5432/max_secretary
uvicorn app.main:app --reload
```

Healthcheck:

```bash
curl http://localhost:8000/api/health
```

PostgreSQL is the only database for dev, production and Docker environments. The application requires `DATABASE_URL` and does not fall back to SQLite.

## Tests

Run from the repository root:

```bash
python -m pytest backend/tests
python -m ruff check backend
```

## Migrations

Run Alembic commands from the `backend` directory with `DATABASE_URL` set:

```bash
alembic revision --autogenerate -m "migration name"
alembic upgrade head
alembic current
```

## Reminder Worker

Reminder jobs run only in the worker process, not inside the FastAPI API process or uvicorn workers.

Production Docker Compose starts the worker with:

```bash
python -m app.workers.jobs
```

Scheduler settings are read from environment variables:

```bash
REMINDERS_ENABLED=true
REMINDER_POLL_INTERVAL_SECONDS=60
DAILY_SUMMARY_TIME=09:00
```

When `REMINDERS_ENABLED=false`, the worker process stays alive but does not start APScheduler. `DAILY_SUMMARY_TIME` uses `HH:MM` in the scheduler timezone, currently UTC. MAX delivery is still a logging stub through `MaxSender`; no real MAX API calls are made.

## MVP Endpoints

- `GET /api/health`
- `POST /api/organizations`, `GET /api/organizations`, `GET /api/organizations/{organization_id}`, `PATCH /api/organizations/{organization_id}`
- `POST /api/users`, `GET /api/users`, `GET /api/users/{user_id}`, `PATCH /api/users/{user_id}`
- `POST /api/chats`, `GET /api/chats`, `GET /api/chats/{chat_id}`, `PATCH /api/chats/{chat_id}`
- `POST /api/chats/{chat_id}/members`, `GET /api/chats/{chat_id}/members`, `PATCH /api/chats/{chat_id}/members/{user_id}`
- `POST /api/tasks`, `GET /api/tasks`, `GET /api/tasks/{task_id}`, `PATCH /api/tasks/{task_id}`, `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/assignees`, `DELETE /api/tasks/{task_id}/assignees/{user_id}`
- `POST /api/tasks/{task_id}/observers`, `DELETE /api/tasks/{task_id}/observers/{user_id}`
- `POST /api/tasks/{task_id}/comments`, `GET /api/tasks/{task_id}/comments`
- `POST /api/tasks/{task_id}/files`, `GET /api/tasks/{task_id}/files`
- `POST /api/tasks/{task_id}/responses`
- `POST /api/tasks/{task_id}/responses/{response_id}/accept`
- `POST /api/tasks/{task_id}/responses/{response_id}/reject`
- `GET /api/tasks/inbox/summary`
- `POST /api/tasks/{task_id}/reminder-rules`, `GET /api/tasks/{task_id}/reminder-rules`, `PATCH /api/tasks/{task_id}/reminder-rules/{rule_id}`, `DELETE /api/tasks/{task_id}/reminder-rules/{rule_id}`
- `POST /api/chats/{chat_id}/reminder-rules`, `GET /api/chats/{chat_id}/reminder-rules`

OpenAPI docs are available at `/docs` when the backend is running.

## Structure

- `app/api` contains HTTP routers with OpenAPI tags.
- `app/core` contains configuration and process-level utilities.
- `app/db` contains database base/session wiring.
- `app/modules` contains domain module boundaries for organizations, chats, users and tasks.
