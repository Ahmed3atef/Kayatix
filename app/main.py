from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sys
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.models.domain import UserSettings
from app.api.v1.endpoints_evaluation import router as evaluation_router
from app.api.v1.endpoints_sourcing import router as sourcing_router
from app.api.v1.endpoints_settings import router as settings_router
from app.api.views import router as views_router

# Setup clean, visible console logging across the entire platform
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger("kayatix.server")

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables automatically on startup (SQLAlchemy checks if tables exist)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Sync UserSettings and Job Templates schema defaults into database (Global Insertion & Schema Sync)
    try:
        from app.services.settings_service import (
            _ensure_schema_columns_exist,
            sync_global_defaults,
            get_or_create_user_settings,
        )
        async with AsyncSessionLocal() as session:
            await _ensure_schema_columns_exist(session)
            await get_or_create_user_settings(session)
            sync_res = await sync_global_defaults(session)
            logger.info(f"[Startup Global Defaults Sync] {sync_res.message}")

            from app.core.database import mask_database_url
            logger.info("=" * 60)
            logger.info(" Kayatix A.Y.A.T. Engine - Active Configuration")
            logger.info(f" -> Database Backend : {mask_database_url(settings.DATABASE_URL)}")
            logger.info(f" -> Google Gemini    : {'[ACTIVE]' if settings.GEMINI_API_KEY else '[NOT SET]'}")
            logger.info(f" -> Groq Cloud       : {'[ACTIVE]' if settings.GROQ_API_KEY else '[NOT SET]'}")
            logger.info(f" -> Ollama Cloud    : {'[ACTIVE]' if settings.OLLAMA_API_KEY else '[NOT SET]'}")
            logger.info(f" -> Google CSE Key   : {'[ACTIVE]' if settings.GOOGLE_CSE_API_KEY else '[NOT SET]'}")
            logger.info(f" -> Google CSE CX    : {'[ACTIVE]' if settings.GOOGLE_CSE_CX_ID else '[NOT SET]'}")
            logger.info(f" -> Evaluation Mode  : {settings.EVALUATION_MODE}")
            logger.info(f" -> Subscription     : {settings.SUBSCRIPTION_TIER.upper()}")
            logger.info("=" * 60)
    except Exception as e:
        logger.error(f"[Startup] Error reading settings from database: {e}", exc_info=True)

    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Multi-Provider AI HR Evaluation & Legal Sourcing Platform (A.Y.A.T. Engine)",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def console_request_logger_middleware(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    if not path.startswith("/static"):
        logger.info(f"==> [{request.method}] {path}")
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    if not path.startswith("/static"):
        logger.info(f"<== [{request.method}] {path} -> {response.status_code} ({duration_ms:.1f}ms)")
    return response

# Mount static directory for Bootstrap assets, custom CSS & JS
static_path = BASE_DIR / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Include UI views router
app.include_router(views_router)

# Include API V1 routers
app.include_router(evaluation_router)
app.include_router(sourcing_router)
app.include_router(settings_router)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "operational", "version": settings.VERSION}
