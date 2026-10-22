"""
Base Declarative registry and async database synchronization helpers.
"""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.database import Base


def utc_now() -> datetime:
    """Returns naive UTC timestamp compatible with both asyncpg PostgreSQL and SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


__all__ = ["Base", "utc_now", "sync_all_models_to_database"]
