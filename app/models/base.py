"""
Base Declarative registry and async database synchronization helpers.
"""

from datetime import datetime
from typing import Any
from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.database import Base
from app.core.timezone import get_current_time, get_app_timezone


def utc_now() -> datetime:
    """
    Returns naive datetime in configured application timezone.
    Retained as an alias for backwards compatibility with all model defaults.
    """
    return get_current_time()


async def sync_all_models_to_database(engine: Any = None) -> None:
    """
    Asynchronously creates and synchronizes all registered SQLAlchemy tables in the database.
    """
    if engine is None:
        from app.core.database import engine as default_engine
        engine = default_engine

    if hasattr(engine, "begin"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        Base.metadata.create_all(bind=engine)


__all__ = ["Base", "get_current_time", "utc_now", "get_app_timezone", "sync_all_models_to_database"]
