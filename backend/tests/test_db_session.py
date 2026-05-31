from __future__ import annotations

import pytest

from app.db import session as session_module


@pytest.mark.anyio
async def test_get_session_opens_session_from_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = object()

    class FakeSessionContext:
        exited = False

        async def __aenter__(self) -> object:
            return fake_session

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            self.exited = True

    context = FakeSessionContext()

    class FakeSessionFactory:
        def __call__(self) -> FakeSessionContext:
            return context

    monkeypatch.setattr(session_module, "get_session_factory", lambda: FakeSessionFactory())

    generator = session_module.get_session()
    yielded_session = await generator.__anext__()

    assert yielded_session is fake_session

    await generator.aclose()

    assert context.exited is True
