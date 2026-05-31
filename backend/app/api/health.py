from fastapi import APIRouter

from app.core.config import DEFAULT_SERVICE_NAME, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name or DEFAULT_SERVICE_NAME}


@router.head("/health")
def health_head() -> None:
    return None
