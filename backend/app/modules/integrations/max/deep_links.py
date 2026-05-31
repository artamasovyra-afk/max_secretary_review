from __future__ import annotations

from urllib.parse import quote


DEFAULT_WEBAPP_STARTAPP = "home"


def normalize_max_bot_username(username: str | None) -> str:
    return (username or "").strip().lstrip("@").strip()


def build_max_webapp_deep_link(
    *,
    bot_username: str | None,
    webapp_base_url: str,
    startapp: str = DEFAULT_WEBAPP_STARTAPP,
    fallback_path: str | None = None,
) -> str:
    normalized_username = normalize_max_bot_username(bot_username)
    if not normalized_username:
        base_url = webapp_base_url.rstrip("/")
        if fallback_path:
            return f"{base_url}/{fallback_path.lstrip('/')}"
        return base_url

    payload = quote(startapp or DEFAULT_WEBAPP_STARTAPP, safe="")
    return f"https://max.ru/{normalized_username}?startapp={payload}"
