from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Response

from app.api.auth import router as auth_router
from app.api.bot_max import router as bot_max_router
from app.api.chats import router as chats_router
from app.api.integrations_bitrix24 import router as integrations_bitrix24_router
from app.core.config import get_settings
from app.api.health import router as health_router
from app.api.organizations import router as organizations_router
from app.api.scheduled_tasks import router as scheduled_tasks_router
from app.api.super_admin import router as super_admin_router
from app.api.task_templates import router as task_templates_router
from app.api.tasks import router as tasks_router
from app.api.users import router as users_router
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if (
        settings.app_env == "production"
        and settings.max_webhook_enabled
        and not settings.max_webhook_secret.get_secret_value()
    ):
        logger.warning("MAX webhook secret is not configured in production.")
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="max_secretary", lifespan=lifespan)

    @app.head("/docs", include_in_schema=False)
    def docs_head() -> Response:
        return Response(status_code=200, media_type="text/html")

    @app.head("/openapi.json", include_in_schema=False)
    def openapi_head() -> Response:
        return Response(status_code=200, media_type="application/json")

    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(organizations_router, prefix="/api/organizations")
    app.include_router(chats_router, prefix="/api/chats")
    app.include_router(users_router, prefix="/api/users")
    app.include_router(tasks_router, prefix="/api/tasks")
    app.include_router(task_templates_router, prefix="/api/task-templates")
    app.include_router(scheduled_tasks_router, prefix="/api/scheduled-tasks")
    app.include_router(super_admin_router, prefix="/api/super-admin")
    app.include_router(bot_max_router, prefix="/api/bot/max")
    app.include_router(integrations_bitrix24_router, prefix="/api/integrations/bitrix24")
    return app


app = create_app()
