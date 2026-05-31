from __future__ import annotations

import logging

from app.core.logging import configure_logging


def test_configure_logging_suppresses_http_client_request_urls() -> None:
    configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
