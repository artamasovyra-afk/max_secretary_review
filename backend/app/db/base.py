from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def import_all_models() -> None:
    """Import model modules so Alembic can discover their metadata."""
    import app.modules.bot.models  # noqa: F401
    import app.modules.chats.models  # noqa: F401
    import app.modules.integrations.models  # noqa: F401
    import app.modules.notifications.models  # noqa: F401
    import app.modules.organizations.models  # noqa: F401
    import app.modules.tasks.models  # noqa: F401
    import app.modules.users.models  # noqa: F401
