from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import engine, Base
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
