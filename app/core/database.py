import logging
import os
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

    # Prevent pytest temporary paths from leaking into runtime
    if "PYTEST_CURRENT_TEST" not in os.environ and "/tmp" in url and ("pytest" in url or "test_switch" in url):
        logger.warning(
            f"[Database] Temporary test path detected in DATABASE_URL ('{url}'). Falling back to '{DEFAULT_SQLITE_URL}'."
        )
        return DEFAULT_SQLITE_URL

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


def mask_database_url(raw_url: str | None) -> str:
    """Masks database password in connection string for secure display in UI and logs."""
    if not raw_url or not raw_url.strip():
        return "Not Configured"
    try:
        parsed = urlparse(raw_url.strip())
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":••••••••@")
            return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        pass
    return raw_url.strip()


class Base(DeclarativeBase):
    pass


def create_engine_for_url(url: str) -> AsyncEngine:
    """
    Builds an AsyncEngine configured with pre-ping validation and connection recycling.

    - pool_pre_ping=True: Emits a lightweight ping whenever checking out a connection
      from the pool. If Neon, Supabase, or any cloud PostgreSQL host dropped the idle TCP socket,
      the dead connection is transparently replaced instead of raising 'InterfaceError: connection is closed'.
    - pool_recycle=300: Refreshes idle connections before remote servers close them.
    - statement_cache_size=0: Prevents prepared statement cache desync when connecting
      through PgBouncer / Neon poolers / Supabase transaction poolers.
    """
    engine_kwargs: dict = {
        "echo": False,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    if "postgresql" in url:
        connect_args: dict = {}
        # Disable prepared statement caching when connecting through transaction poolers
        if any(h in url for h in ["-pooler", "pooler", "pgbouncer", "neon.tech", "supabase"]):
            connect_args["statement_cache_size"] = 0
            connect_args["command_timeout"] = 60
        if connect_args:
            engine_kwargs["connect_args"] = connect_args
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20
    return create_async_engine(url, **engine_kwargs)


engine: AsyncEngine = create_engine_for_url(normalize_database_url(settings.DATABASE_URL))
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def switch_database_engine(new_url: str) -> str:
    """
    Switches active database engine at runtime and creates schema if missing.
    Returns normalized URL.
    """
    global engine, AsyncSessionLocal
    normalized = normalize_database_url(new_url)
    old_engine = engine

    new_engine = create_engine_for_url(normalized)
    async with new_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
