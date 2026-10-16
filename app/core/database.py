import logging
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./hr_copilot.db"


def normalize_database_url(raw_url: str | None) -> str:
    """
    Normalizes user-supplied database connection strings for SQLAlchemy AsyncEngine:
    - Automatically maps 'postgresql://' or 'postgres://' to 'postgresql+asyncpg://'.
    - Converts 'sslmode=...' to 'ssl=...' for asyncpg driver compatibility.
    - Strips unsupported libpq parameters like 'channel_binding'.
    - Preserves and standardizes SQLite aiosqlite strings.
    """
    if not raw_url or not raw_url.strip():
        return DEFAULT_SQLITE_URL
    url = raw_url.strip()

    if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")

    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    if url.startswith("postgresql+asyncpg://"):
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        filtered_params = {}
        for k, v in params.items():
            if k in ["sslmode", "ssl"]:
                filtered_params["ssl"] = v[0]
            elif k == "channel_binding":
                continue
            else:
                filtered_params[k] = v[0]

        # For cloud postgres hosts like neon.tech or supabase, ensure ssl is required
        if "ssl" not in filtered_params and any(h in parsed.netloc for h in ["neon.tech", "supabase", "aws", "pooler"]):
            filtered_params["ssl"] = "require"

        new_query = urlencode(filtered_params)
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    return url


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(normalize_database_url(settings.DATABASE_URL), echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def switch_database_engine(new_url: str) -> str:
    """
    Switches active database engine at runtime and creates schema if missing.
    Returns normalized URL.
    """
    global engine, AsyncSessionLocal
    normalized = normalize_database_url(new_url)
    old_engine = engine

    new_engine = create_async_engine(normalized, echo=False)
    async with new_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def migrate_schema(sync_conn):
            try:
                sync_conn.exec_driver_sql(
                    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS database_url VARCHAR(1024)"
                )
                sync_conn.exec_driver_sql(
                    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS evaluation_mode VARCHAR(50) DEFAULT 'llm_cascade'"
                )
            except Exception:
                try:
                    res = sync_conn.exec_driver_sql("PRAGMA table_info(user_settings)").fetchall()
                    existing_cols = {row[1] for row in res}
                    if existing_cols:
                        if "database_url" not in existing_cols:
                            sync_conn.exec_driver_sql(
                                "ALTER TABLE user_settings ADD COLUMN database_url VARCHAR(1024)"
                            )
                        if "evaluation_mode" not in existing_cols:
                            sync_conn.exec_driver_sql(
                                "ALTER TABLE user_settings ADD COLUMN evaluation_mode VARCHAR(50) DEFAULT 'llm_cascade'"
                            )
                except Exception:
                    pass

        await conn.run_sync(migrate_schema)

    try:
        await old_engine.dispose()
    except Exception as e:
        logger.warning(f"Error disposing old engine: {e}")

    engine = new_engine
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    settings.DATABASE_URL = normalized
    return normalized


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
