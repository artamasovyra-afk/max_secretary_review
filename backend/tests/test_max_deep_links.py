from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.modules.integrations.max.deep_links import build_max_webapp_deep_link, normalize_max_bot_username


def test_build_max_webapp_deep_link_with_username() -> None:
    assert (
        build_max_webapp_deep_link(
            bot_username="secretary_oren_bot",
            webapp_base_url="https://maxsecretary.ru",
            startapp="home",
        )
        == "https://max.ru/secretary_oren_bot?startapp=home"
    )


def test_build_max_webapp_deep_link_strips_leading_at() -> None:
    assert normalize_max_bot_username(" @secretary_oren_bot ") == "secretary_oren_bot"
    assert (
        build_max_webapp_deep_link(
            bot_username="@secretary_oren_bot",
            webapp_base_url="https://maxsecretary.ru",
            startapp="home",
        )
        == "https://max.ru/secretary_oren_bot?startapp=home"
    )


def test_build_max_webapp_deep_link_urlencodes_payload() -> None:
    assert (
        build_max_webapp_deep_link(
            bot_username="secretary_oren_bot",
            webapp_base_url="https://maxsecretary.ru",
            startapp="task 123",
        )
        == "https://max.ru/secretary_oren_bot?startapp=task%20123"
    )


def test_build_max_webapp_deep_link_falls_back_to_webapp_base_url() -> None:
    assert (
        build_max_webapp_deep_link(
            bot_username="",
            webapp_base_url="https://maxsecretary.ru/",
            startapp="home",
        )
        == "https://maxsecretary.ru"
    )


def test_build_max_webapp_deep_link_fallback_path() -> None:
    assert (
        build_max_webapp_deep_link(
            bot_username=None,
            webapp_base_url="https://maxsecretary.ru/",
            startapp="task_mock",
            fallback_path="/tasks/mock",
        )
        == "https://maxsecretary.ru/tasks/mock"
    )


def test_generated_deep_link_contains_no_sensitive_context() -> None:
    url = build_max_webapp_deep_link(
        bot_username="secretary_oren_bot",
        webapp_base_url="https://maxsecretary.ru",
        startapp="assign_88888888-8888-4888-8888-888888888888",
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert "user_id" not in query
    assert "token" not in query
    assert "secret" not in query
