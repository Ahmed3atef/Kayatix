from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
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

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite/PostgreSQL tables automatically on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Self-healing column migration for SQLite
        def migrate_schema(sync_conn):
            try:
                res = sync_conn.exec_driver_sql("PRAGMA table_info(user_settings)").fetchall()
                existing_cols = {row[1] for row in res}
                if existing_cols and "evaluation_mode" not in existing_cols:
                    sync_conn.exec_driver_sql(
                        "ALTER TABLE user_settings ADD COLUMN evaluation_mode VARCHAR(50) DEFAULT 'hybrid'"
                    )
            except Exception:
                pass

        await conn.run_sync(migrate_schema)

    # Sync UserSettings from SQLite DB into runtime in-memory settings
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(UserSettings)
            user_settings = (await session.execute(stmt)).scalars().first()
            if user_settings:
                if user_settings.gemini_api_key:
                    settings.GEMINI_API_KEY = user_settings.gemini_api_key
                if user_settings.groq_api_key:
                    settings.GROQ_API_KEY = user_settings.groq_api_key
                if user_settings.openrouter_api_key:
                    settings.OPENROUTER_API_KEY = user_settings.openrouter_api_key
                if user_settings.google_cse_api_key:
                    settings.GOOGLE_CSE_API_KEY = user_settings.google_cse_api_key
                if user_settings.google_cse_cx_id:
                    settings.GOOGLE_CSE_CX_ID = user_settings.google_cse_cx_id
                if user_settings.evaluation_mode:
                    settings.EVALUATION_MODE = user_settings.evaluation_mode
    except Exception:
        pass

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
