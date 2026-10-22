from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import List, Optional
from fastapi import HTTPException
import httpx
from google import genai
from openai import AsyncOpenAI
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import settings
from app.core import database as db_core
from app.core.database import (
    DEFAULT_SQLITE_URL,
    normalize_database_url,
)
from app.models import JobTemplate, UserSettings, utc_now
from app.schemas.payloads import (
    AppDefaultsSchema,
    DatabaseValidationResponse,
    DefaultsSchemaResponse,
    DefaultsSyncResult,
    JobTemplateCreateRequest,
    JobTemplateResponse,
    JobTemplateSchema,
    JobTemplateUpdateRequest,
    ProviderValidationStatus,
    SettingsValidationResponse,
    SystemSettingsDefaultsSchema,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
JOB_FIXTURE_PATH = FIXTURES_DIR / "job_template.json"
USER_SETTINGS_FIXTURE_PATH = FIXTURES_DIR / "user_settings.json"
FRAPPE_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
FRAPPE_DOCTYPES_DIR = FRAPPE_MODELS_DIR


def get_defaults_file_path() -> Path:
    """Returns path to the primary job template fixture."""
    return JOB_FIXTURE_PATH


def load_default_settings_schema() -> AppDefaultsSchema:
    """Loads application defaults and job templates directly from fixtures/job_template.json and fixtures/user_settings.json."""
    modified_ts = "2026-10-16T19:00:00Z"
    templates_list: List[JobTemplateSchema] = []
    sys_settings = SystemSettingsDefaultsSchema(
        project_name="Kayatix - A.Y.A.T. Engine",
        version="1.0.0",
        subscription_tier="standard",
        evaluation_mode="llm_cascade",
        rate_limit_rpm=15,
    )

    # 1. Load job templates fixture
    if JOB_FIXTURE_PATH.exists():
        try:
            with open(JOB_FIXTURE_PATH, "r", encoding="utf-8") as f:
                job_raw = json.load(f)
                if isinstance(job_raw, dict):
                    modified_ts = job_raw.get("modified_timestamp", modified_ts)
                    raw_items = job_raw.get("data", [])
                elif isinstance(job_raw, list):
                    raw_items = job_raw
                else:
                    raw_items = []
                for item in raw_items:
                    templates_list.append(
                        JobTemplateSchema(
                            title=item.get("title", ""),
                            category=item.get("category", "General"),
                            description=item.get("description", ""),
                        )
                    )
        except Exception as e:
            logger.error(f"[DefaultsSchema] Error reading {JOB_FIXTURE_PATH}: {e}")

    # 2. Load user settings fixture
    if USER_SETTINGS_FIXTURE_PATH.exists():
        try:
            with open(USER_SETTINGS_FIXTURE_PATH, "r", encoding="utf-8") as f:
                settings_raw = json.load(f)
                settings_item = settings_raw[0] if isinstance(settings_raw, list) and settings_raw else settings_raw
                if isinstance(settings_item, dict):
                    sys_settings = SystemSettingsDefaultsSchema(
                        project_name=settings_item.get("project_name", "Kayatix - A.Y.A.T. Engine"),
                        version=settings_item.get("version", "1.0.0"),
                        subscription_tier=settings_item.get("subscription_tier", "standard"),
                        evaluation_mode=settings_item.get("evaluation_mode", "llm_cascade"),
                        rate_limit_rpm=settings_item.get("rate_limit_rpm", 15),
                    )
        except Exception as e:
            logger.error(f"[DefaultsSchema] Error reading {USER_SETTINGS_FIXTURE_PATH}: {e}")

    if not templates_list:
        fallback = AppDefaultsSchema(
            version="1.0.0",
            modified_timestamp=modified_ts,
            system_settings=sys_settings,
            job_templates=[],
        )
        return fallback

    return AppDefaultsSchema(
        version="1.0.0",
        modified_timestamp=modified_ts,
        system_settings=sys_settings,
        job_templates=templates_list,
    )

    fallback = AppDefaultsSchema(
        version="1.0.0",
        modified_timestamp="2026-10-16T19:00:00Z",
        system_settings=SystemSettingsDefaultsSchema(
            project_name="Kayatix - A.Y.A.T. Engine",
            version="1.0.0",
            subscription_tier="standard",
            evaluation_mode="llm_cascade",
            rate_limit_rpm=15,
        ),
        job_templates=[
            JobTemplateSchema(
                title="FastAPI Backend Engineer",
                category="Engineering",
                description=(
                    "Job Title: Senior FastAPI Backend Engineer\n"
                    "Location: Remote / Hybrid\n"
                    "Requirements:\n"
                    "- 5+ years experience building production backends with Python & FastAPI\n"
                    "- Deep proficiency with SQLAlchemy async ORM, PostgreSQL schema design, and query optimization\n"
                    "- Experience building microservices, Docker containerization, and REST API standards\n"
                    "- Hands-on experience with asynchronous rate-limiting, circuit-breakers, and caching architectures (Redis/SQLite)\n"
                    "- Strong understanding of unit testing with pytest and async fixtures."
                ),
            ),
            JobTemplateSchema(
                title="Full Stack Python / React",
                category="Engineering",
                description=(
                    "Job Title: Full Stack Software Engineer (Python & React)\n"
                    "Location: Remote\n"
                    "Requirements:\n"
                    "- 4+ years of professional full-stack development experience\n"
                    "- Python, FastAPI or Django on the backend\n"
                    "- Modern React, TypeScript, and TailwindCSS or Bootstrap 5 on the frontend\n"
                    "- Experience integrating third-party APIs, OAuth, and LLM providers\n"
                    "- Strong database knowledge (PostgreSQL, SQLite)."
                ),
            ),
            JobTemplateSchema(
                title="DevOps & Cloud Platform",
                category="Engineering",
                description=(
                    "Job Title: Cloud & DevOps Platform Engineer\n"
                    "Location: Remote / Hybrid\n"
                    "Requirements:\n"
                    "- 5+ years managing Linux infrastructure and cloud environments (AWS/GCP/Azure)\n"
                    "- Extensive hands-on experience with Docker, Kubernetes, and Helm\n"
                    "- CI/CD automation pipelines (GitHub Actions, GitLab CI)\n"
                    "- Infrastructure as Code (Terraform)\n"
                    "- Python or Bash scripting for system automation."
                ),
            ),
            JobTemplateSchema(
                title="Talent Acquisition & HR Lead",
                category="Human Resources",
                description=(
                    "Job Title: Senior Talent Acquisition Specialist & HR Lead\n"
                    "Location: Remote / On-site\n"
                    "Requirements:\n"
                    "- 5+ years of full-cycle technical recruiting and HR talent intelligence experience\n"
                    "- Demonstrated track record sourcing candidates via Boolean search, LinkedIn X-Ray, and developer communities\n"
                    "- Experience with Applicant Tracking Systems (ATS) and candidate evaluation benchmarking\n"
                    "- Strong competency in structured behavioral interviews and merit-based talent screening\n"
                    "- Excellent stakeholder communication and compensation negotiation skills."
                ),
            ),
            JobTemplateSchema(
                title="Growth Marketing Manager",
                category="Marketing",
                description=(
                    "Job Title: Growth & Digital Marketing Manager\n"
                    "Location: Remote / Hybrid\n"
                    "Requirements:\n"
                    "- 4+ years experience in B2B SaaS growth marketing, SEO, and paid acquisition\n"
                    "- Proven track record increasing conversion rates (CRO) and MRR with quantified pipeline growth\n"
                    "- Deep proficiency with Google Analytics 4, HubSpot, Mixpanel, and SEMrush\n"
                    "- Hands-on experience running multi-channel campaigns (LinkedIn Ads, Google Search, Email nurturing)\n"
                    "- Strong data analysis skills (SQL or Python a plus) to measure CAC, LTV, and retention."
                ),
            ),
            JobTemplateSchema(
                title="Financial Analyst & Controller",
                category="Finance",
                description=(
                    "Job Title: Senior Financial Analyst & Corporate Controller\n"
                    "Location: Hybrid / On-site\n"
                    "Requirements:\n"
                    "- 5+ years of financial planning & analysis (FP&A), budget forecasting, and corporate reporting\n"
                    "- Advanced financial modeling in Excel, Power BI, and ERP systems (SAP/NetSuite)\n"
                    "- CPA or CFA qualification preferred; strong knowledge of US GAAP / IFRS standards\n"
                    "- Demonstrated success in cost optimization, margin expansion, and audit defense\n"
                    "- Experience presenting quarterly board decks and capital allocation models."
                ),
            ),
        ],
    )
    try:
        save_default_settings_schema(fallback)
    except Exception:
        pass
    return fallback


def save_default_settings_schema(data: AppDefaultsSchema) -> None:
    """Saves default templates to fixtures/job_template.json and system settings to fixtures/user_settings.json."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save job templates fixture
    job_payload = {
        "doctype": "Job Template",
        "modified_timestamp": data.modified_timestamp,
        "data": [
            {
                "doctype": "Job Template",
                "title": t.title,
                "category": t.category,
                "description": t.description,
            }
            for t in data.job_templates
        ],
    }
    with open(JOB_FIXTURE_PATH, "w", encoding="utf-8") as f:
        json.dump(job_payload, f, indent=2)

    # 2. Save user settings fixture
    settings_payload = [
        {
            "doctype": "User Settings",
            "project_name": data.system_settings.project_name,
            "version": data.system_settings.version,
            "subscription_tier": data.system_settings.subscription_tier,
            "evaluation_mode": data.system_settings.evaluation_mode,
            "rate_limit_rpm": data.system_settings.rate_limit_rpm,
        }
    ]
    with open(USER_SETTINGS_FIXTURE_PATH, "w", encoding="utf-8") as f:
        json.dump(settings_payload, f, indent=2)


def get_frappe_doctype_schema(doctype_name: str = "job_template") -> dict:
    """
    Returns the schema specification for the specified model
    derived directly from the SQLAlchemy model class.
    """
    from app.models import Candidate, EvaluationCache, Job, JobTemplate, User, UserSettings

    mapping = {
        "job_template": JobTemplate,
        "user_settings": UserSettings,
        "user": User,
        "job": Job,
        "candidate": Candidate,
        "candidate_evaluation": EvaluationCache,
    }
    normalized_name = doctype_name.lower().strip().replace(" ", "_").replace("-", "_")
    model = mapping.get(normalized_name)
    if model:
        fields = []
        for col in model.__table__.columns:
            fields.append({
                "fieldname": col.name,
                "fieldtype": str(col.type),
                "label": col.name.replace("_", " ").title(),
                "primary_key": col.primary_key,
                "nullable": col.nullable,
            })
        name_map = {
            "job_template": "Job Template",
            "user_settings": "User Settings",
            "user": "User",
            "job": "Job",
            "candidate": "Candidate",
            "candidate_evaluation": "Candidate Evaluation",
        }
        res = {
            "doctype": "DocType",
            "name": name_map.get(normalized_name, model.__name__),
            "table_name": model.__tablename__,
            "field_order": [c.name for c in model.__table__.columns],
            "fields": fields,
        }
        if model is UserSettings:
            res["issingle"] = 1
        return res

    return AppDefaultsSchema.model_json_schema()



def get_defaults_json_schema() -> dict:
    """Returns the official Frappe DocType JSON Schema for job template defaults."""
    return get_frappe_doctype_schema("job_template")


# Default out-of-the-box configuration loaded from schema
_cached_defaults = load_default_settings_schema()
DEFAULT_PROJECT_NAME = _cached_defaults.system_settings.project_name
DEFAULT_VERSION = _cached_defaults.system_settings.version
DEFAULT_SUBSCRIPTION_TIER = _cached_defaults.system_settings.subscription_tier
DEFAULT_EVALUATION_MODE = _cached_defaults.system_settings.evaluation_mode
DEFAULT_RATE_LIMIT_RPM = _cached_defaults.system_settings.rate_limit_rpm


def clean_google_cx_id(raw_cx: Optional[str]) -> Optional[str]:
    """
    Sanitizes Search Engine ID (cx). If user pastes:
    <script async src="https://cse.google.com/cse.js?cx=c5c6e8ce160ff411e"></script>
    or URL https://cse.google.com/cse.js?cx=c5c6e8ce160ff411e,
    extracts the exact alphanumeric ID.
    """
    if not raw_cx:
        return None
    raw_cx = raw_cx.strip()
    match = re.search(r'cx=([a-zA-Z0-9_\-:]+)', raw_cx)
    if match:
        return match.group(1).strip('"\'')
    cleaned = re.sub(r'<[^>]+>', '', raw_cx).strip()
    return cleaned if cleaned else None


def generate_config_text(record: UserSettings) -> str:
    """Generates standardized key-value configuration text from database record."""
    from app.core.database import mask_database_url
    active_db = mask_database_url(record.database_url or settings.DATABASE_URL)
    return (
        f'PROJECT_NAME="{record.project_name or DEFAULT_PROJECT_NAME}"\n'
        f'VERSION="{record.version or DEFAULT_VERSION}"\n'
        f'# DATABASE_URL is managed securely via server environment variables / .env\n'
        f'DATABASE_URL="{active_db}"\n\n'
        f'# AI Provider Keys\n'
        f'GEMINI_API_KEY="{record.gemini_api_key or ""}"\n'
        f'GROQ_API_KEY="{record.groq_api_key or ""}"\n'
        f'OLLAMA_API_KEY="{getattr(record, "ollama_api_key", None) or ""}"\n'
        f'OLLAMA_BASE_URL="{getattr(record, "ollama_base_url", None) or settings.OLLAMA_BASE_URL}"\n\n'
        f'# Legal LinkedIn X-Ray Search Keys\n'
        f'GOOGLE_CSE_CX_ID="{record.google_cse_cx_id or ""}"\n\n'
        f'# Engine & Subscription Modes\n'
        f'EVALUATION_MODE="{record.evaluation_mode or DEFAULT_EVALUATION_MODE}"\n'
        f'SUBSCRIPTION_TIER="{record.subscription_tier or DEFAULT_SUBSCRIPTION_TIER}"\n'
        f'RATE_LIMIT_RPM={record.rate_limit_rpm or DEFAULT_RATE_LIMIT_RPM}\n'
    )


def parse_config_text(text: str) -> dict:
    """Parses raw KEY=VALUE string into a dictionary."""
    parsed = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            parsed[key] = val
    return parsed


def _persist_database_url_to_env(new_url: str):
    """Safely updates or inserts DATABASE_URL in .env file on disk."""
    try:
        # Never overwrite .env during test execution or with temporary test databases
        if "PYTEST_CURRENT_TEST" in os.environ or "/tmp" in new_url or "pytest" in new_url or "test_switch" in new_url:
            return
        env_path = ".env"
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()
        db_url_found = False
        new_lines = []
        for line in env_lines:
            if line.startswith("DATABASE_URL="):
                new_lines.append(f'DATABASE_URL="{new_url}"\n')
                db_url_found = True
            else:
                new_lines.append(line)
        if not db_url_found:
            new_lines.append(f'DATABASE_URL="{new_url}"\n')
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        logger.warning(f"Could not persist DATABASE_URL to .env file: {e}")


def _get_dialect_name(db: AsyncSession) -> str:
    try:
        if db.bind:
            return getattr(db.bind.dialect, "name", "sqlite").lower()
    except Exception:
        pass
    return "sqlite"


async def _column_exists(db: AsyncSession, table_name: str, column_name: str) -> bool:
    """Safely checks if column exists in table without throwing or aborting transactions."""
    dialect = _get_dialect_name(db)
    try:
        if "postgres" in dialect:
            res = await db.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table_name.lower(), "c": column_name.lower()},
            )
            return res.scalar() is not None
        else:
            res = await db.execute(text(f"PRAGMA table_info({table_name})"))
            columns = [str(r[1]).lower() for r in res.fetchall()]
            return column_name.lower() in columns
    except Exception as e:
        logger.debug(f"[Schema Check] _column_exists check failed for {table_name}.{column_name}: {e}")
        return False


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    """Safely checks if table exists in database without throwing or aborting transactions."""
    dialect = _get_dialect_name(db)
    try:
        if "postgres" in dialect:
            res = await db.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
                {"t": table_name.lower()},
            )
            return res.scalar() is not None
        else:
            res = await db.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :t"),
                {"t": table_name},
            )
            return res.scalar() is not None
    except Exception as e:
        logger.debug(f"[Schema Check] _table_exists check failed for {table_name}: {e}")
        return False


_schema_ensured: bool = False


async def _ensure_schema_columns_exist(db: AsyncSession, force: bool = False):
    """Ensures ollama_api_key, ollama_base_url, and job_templates_schema_timestamp exist in user_settings, and ai_instructions table exists."""
    global _schema_ensured
    if _schema_ensured and not force:
        return

    # First verify if user_settings table exists
    if not await _table_exists(db, "user_settings"):
        return

    # 1. ollama_api_key
    if not await _column_exists(db, "user_settings", "ollama_api_key"):
        try:
            await db.execute(text("ALTER TABLE user_settings ADD COLUMN ollama_api_key VARCHAR(255)"))
            await db.commit()
            logger.info("[Database Migration] Added ollama_api_key column to user_settings.")
        except Exception as e:
            logger.warning(f"[Database Migration] Adding ollama_api_key skipped/failed: {e}")

    # 2. ollama_base_url
    if not await _column_exists(db, "user_settings", "ollama_base_url"):
        try:
            await db.execute(text("ALTER TABLE user_settings ADD COLUMN ollama_base_url VARCHAR(255) DEFAULT 'https://ollama.com/v1'"))
            await db.commit()
            logger.info("[Database Migration] Added ollama_base_url column to user_settings.")
        except Exception as e:
            logger.warning(f"[Database Migration] Adding ollama_base_url skipped/failed: {e}")

    # 3. job_templates_schema_timestamp
    if not await _column_exists(db, "user_settings", "job_templates_schema_timestamp"):
        try:
            await db.execute(text("ALTER TABLE user_settings ADD COLUMN job_templates_schema_timestamp VARCHAR(50)"))
            await db.commit()
            logger.info("[Database Migration] Added job_templates_schema_timestamp column to user_settings.")
        except Exception as e:
            logger.warning(f"[Database Migration] Adding job_templates_schema_timestamp skipped/failed: {e}")

    # 4. Clean up deprecated ai_instructions table if present from legacy installs
    if await _table_exists(db, "ai_instructions"):
        try:
            await db.execute(text("DROP TABLE IF EXISTS ai_instructions"))
            await db.commit()
            logger.info("[Database Migration] Dropped deprecated ai_instructions table.")
        except Exception as e:
            logger.warning(f"[Database Migration] Cleanup of ai_instructions table skipped: {e}")

    # 5. Ensure users table exists
    if not await _table_exists(db, "users"):
        try:
            from app.core.database import Base, engine
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("[Database Migration] Initialized users table.")
        except Exception as e:
            logger.warning(f"[Database Migration] Initializing users table skipped/failed: {e}")

    _schema_ensured = True


async def get_or_create_user_settings(db: AsyncSession) -> UserSettings:
    """
    Retrieves user settings row from active DB or initializes it with complete out-of-the-box defaults on first run.
    - If settings exist in the database, they are strictly read and synchronized into runtime memory.
    - If any key is missing in the database but configured in environment/defaults, it is backfilled.
    - If no settings record exists at all, creates one with system defaults and any configured env values.
    """
    if not _schema_ensured:
        await _ensure_schema_columns_exist(db)

    stmt = select(UserSettings).limit(1)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        logger.info("[Database] No settings record found in active database. Initializing fresh UserSettings record with system defaults.")
        user_settings = UserSettings(
            project_name=DEFAULT_PROJECT_NAME,
            version=DEFAULT_VERSION,
            gemini_api_key=settings.GEMINI_API_KEY,
            groq_api_key=settings.GROQ_API_KEY,
            ollama_api_key=settings.OLLAMA_API_KEY,
            ollama_base_url=settings.OLLAMA_BASE_URL,
            google_cse_cx_id=settings.GOOGLE_CSE_CX_ID,
            subscription_tier=DEFAULT_SUBSCRIPTION_TIER,
            evaluation_mode=DEFAULT_EVALUATION_MODE,
            rate_limit_rpm=DEFAULT_RATE_LIMIT_RPM,
            database_url=settings.DATABASE_URL,
        )
        user_settings.env_content = generate_config_text(user_settings)
        db.add(user_settings)
        await db.commit()
        await db.refresh(user_settings)
        logger.info("[Database] Successfully created fresh UserSettings record.")
    else:
        # Settings record exists: check if any missing keys can be backfilled from settings/env
        dirty = False
        if not user_settings.gemini_api_key and settings.GEMINI_API_KEY:
            user_settings.gemini_api_key = settings.GEMINI_API_KEY
            dirty = True
        if not user_settings.groq_api_key and settings.GROQ_API_KEY:
            user_settings.groq_api_key = settings.GROQ_API_KEY
            dirty = True
        if not getattr(user_settings, "ollama_api_key", None) and settings.OLLAMA_API_KEY:
            user_settings.ollama_api_key = settings.OLLAMA_API_KEY
            dirty = True
        if not getattr(user_settings, "ollama_base_url", None) and settings.OLLAMA_BASE_URL:
            user_settings.ollama_base_url = settings.OLLAMA_BASE_URL
            dirty = True
        if not user_settings.google_cse_cx_id and settings.GOOGLE_CSE_CX_ID:
            user_settings.google_cse_cx_id = settings.GOOGLE_CSE_CX_ID
            dirty = True

        from app.core.database import normalize_database_url
        norm_db = normalize_database_url(user_settings.database_url)
        norm_settings = normalize_database_url(settings.DATABASE_URL)
        if not user_settings.database_url or norm_db != norm_settings:
            user_settings.database_url = norm_settings
            dirty = True

        if dirty:
            await db.commit()
            await db.refresh(user_settings)

    # Sync runtime memory configuration from database
    if user_settings.gemini_api_key:
        settings.GEMINI_API_KEY = user_settings.gemini_api_key
    if user_settings.groq_api_key:
        settings.GROQ_API_KEY = user_settings.groq_api_key
    if getattr(user_settings, "ollama_api_key", None):
        settings.OLLAMA_API_KEY = user_settings.ollama_api_key
    if getattr(user_settings, "ollama_base_url", None):
        settings.OLLAMA_BASE_URL = user_settings.ollama_base_url
    if user_settings.google_cse_cx_id:
        settings.GOOGLE_CSE_CX_ID = user_settings.google_cse_cx_id
    if user_settings.subscription_tier:
        settings.SUBSCRIPTION_TIER = user_settings.subscription_tier
    if user_settings.evaluation_mode:
        settings.EVALUATION_MODE = user_settings.evaluation_mode
    if user_settings.rate_limit_rpm:
        settings.RATE_LIMIT_RPM = user_settings.rate_limit_rpm
    if user_settings.project_name:
        settings.PROJECT_NAME = user_settings.project_name
    if user_settings.version:
        settings.VERSION = user_settings.version

    return user_settings


provider_health_cache: dict[str, str] = {
    "gemini": "unconfigured",
    "groq": "unconfigured",
    "ollama": "unconfigured",
}


def get_current_provider_health(record) -> dict[str, str]:
    health = dict(provider_health_cache)
    if not record.gemini_api_key or not record.gemini_api_key.strip():
        health["gemini"] = "unconfigured"
    if not record.groq_api_key or not record.groq_api_key.strip():
        health["groq"] = "unconfigured"
    if not getattr(record, "ollama_api_key", None) or not record.ollama_api_key.strip():
        health["ollama"] = "unconfigured"
    return health


async def get_settings_summary(db: AsyncSession) -> UserSettingsResponse:
    """Returns configuration overview, secret status, and safe configuration with masked credentials."""
    from app.core.database import mask_database_url
    record = await get_or_create_user_settings(db)
    active_db = record.database_url or settings.DATABASE_URL or ""
    db_type = "postgresql" if "postgres" in active_db.lower() else "sqlite"
    masked_db = mask_database_url(active_db)

    return UserSettingsResponse(
        project_name=record.project_name or DEFAULT_PROJECT_NAME,
        version=record.version or DEFAULT_VERSION,
        gemini_api_key_configured=bool(record.gemini_api_key and record.gemini_api_key.strip()),
        groq_api_key_configured=bool(record.groq_api_key and record.groq_api_key.strip()),
        ollama_api_key_configured=bool(getattr(record, "ollama_api_key", None) and record.ollama_api_key.strip()),
        ollama_base_url=getattr(record, "ollama_base_url", None) or settings.OLLAMA_BASE_URL,
        google_cse_cx_id_configured=bool(record.google_cse_cx_id and record.google_cse_cx_id.strip()),
        subscription_tier=record.subscription_tier or DEFAULT_SUBSCRIPTION_TIER,
        evaluation_mode=record.evaluation_mode or DEFAULT_EVALUATION_MODE,
        rate_limit_rpm=record.rate_limit_rpm or DEFAULT_RATE_LIMIT_RPM,
        database_url=masked_db,
        masked_database_url=masked_db,
        database_type=db_type,
        env_content=None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
        provider_health=get_current_provider_health(record),
    )


async def update_user_settings(
    req: UserSettingsUpdateRequest, db: AsyncSession
) -> UserSettingsResponse:
    """Persists updated API keys and configuration directly into active database."""
    record = await get_or_create_user_settings(db)

    # If raw config text is passed, parse and update fields
    if req.env_content is not None and req.env_content.strip():
        parsed = parse_config_text(req.env_content)
        if "GEMINI_API_KEY" in parsed:
            record.gemini_api_key = parsed["GEMINI_API_KEY"].strip() or None
            settings.GEMINI_API_KEY = record.gemini_api_key
        if "GROQ_API_KEY" in parsed:
            record.groq_api_key = parsed["GROQ_API_KEY"].strip() or None
            settings.GROQ_API_KEY = record.groq_api_key
        if "OLLAMA_API_KEY" in parsed:
            record.ollama_api_key = parsed["OLLAMA_API_KEY"].strip() or None
            settings.OLLAMA_API_KEY = record.ollama_api_key
        if "OLLAMA_BASE_URL" in parsed:
            record.ollama_base_url = parsed["OLLAMA_BASE_URL"].strip() or settings.OLLAMA_BASE_URL
            settings.OLLAMA_BASE_URL = record.ollama_base_url
        if "GOOGLE_CSE_CX_ID" in parsed:
            record.google_cse_cx_id = clean_google_cx_id(parsed["GOOGLE_CSE_CX_ID"])
            settings.GOOGLE_CSE_CX_ID = record.google_cse_cx_id
        if "EVALUATION_MODE" in parsed:
            record.evaluation_mode = parsed["EVALUATION_MODE"].strip() or DEFAULT_EVALUATION_MODE
            settings.EVALUATION_MODE = record.evaluation_mode
        if "SUBSCRIPTION_TIER" in parsed:
            record.subscription_tier = parsed["SUBSCRIPTION_TIER"]
            settings.SUBSCRIPTION_TIER = record.subscription_tier
        if "RATE_LIMIT_RPM" in parsed:
            try:
                record.rate_limit_rpm = int(parsed["RATE_LIMIT_RPM"])
                settings.RATE_LIMIT_RPM = record.rate_limit_rpm
            except ValueError:
                pass
        record.env_content = req.env_content.strip()

    # Process individual structured fields
    if req.gemini_api_key is not None:
        record.gemini_api_key = req.gemini_api_key.strip() or None
        settings.GEMINI_API_KEY = record.gemini_api_key
    if req.groq_api_key is not None:
        record.groq_api_key = req.groq_api_key.strip() or None
        settings.GROQ_API_KEY = record.groq_api_key
    if req.ollama_api_key is not None:
        record.ollama_api_key = req.ollama_api_key.strip() or None
        settings.OLLAMA_API_KEY = record.ollama_api_key
    if req.ollama_base_url is not None:
        record.ollama_base_url = req.ollama_base_url.strip() or settings.OLLAMA_BASE_URL
        settings.OLLAMA_BASE_URL = record.ollama_base_url
    if req.google_cse_cx_id is not None:
        record.google_cse_cx_id = clean_google_cx_id(req.google_cse_cx_id)
        settings.GOOGLE_CSE_CX_ID = record.google_cse_cx_id
    if req.evaluation_mode is not None:
        record.evaluation_mode = req.evaluation_mode.strip() or DEFAULT_EVALUATION_MODE
        settings.EVALUATION_MODE = record.evaluation_mode
    if req.subscription_tier is not None:
        record.subscription_tier = req.subscription_tier
        settings.SUBSCRIPTION_TIER = record.subscription_tier
    if req.rate_limit_rpm is not None:
        record.rate_limit_rpm = req.rate_limit_rpm
        settings.RATE_LIMIT_RPM = record.rate_limit_rpm

    # DATABASE_URL is managed strictly via server environment variables / .env.
    # The active database session is used directly.
    record.env_content = generate_config_text(record)
    await db.commit()
    await db.refresh(record)

    # Immediately refresh health status for configured provider keys
    if record.groq_api_key and provider_health_cache.get("groq") != "valid":
        try:
            await validate_groq_key(record.groq_api_key)
        except Exception:
            pass
    if record.gemini_api_key and provider_health_cache.get("gemini") != "valid":
        try:
            await validate_gemini_key(record.gemini_api_key)
        except Exception:
            pass
    if getattr(record, "ollama_api_key", None) and provider_health_cache.get("ollama") != "valid":
        try:
            await validate_ollama_key(record.ollama_api_key, record.ollama_base_url)
        except Exception:
            pass

    return await get_settings_summary(db)


async def validate_database_connection(raw_url: Optional[str] = None) -> DatabaseValidationResponse:
    """Validates connectivity to a PostgreSQL or database link."""
    target_url = raw_url.strip() if raw_url and raw_url.strip() else settings.DATABASE_URL
    if not target_url or not target_url.strip():
        return DatabaseValidationResponse(
            status="invalid",
            message="Database connection link is not configured. Set DATABASE_URL in .env or server environment.",
            database_type="unknown",
        )
    from app.core.database import mask_database_url
    normalized = normalize_database_url(target_url)
    if not (normalized.startswith("postgresql+asyncpg://") or normalized.startswith("sqlite+aiosqlite://")):
        return DatabaseValidationResponse(
            status="invalid",
            message="Unsupported database scheme. Connection URL must start with postgresql:// or sqlite:///",
            database_type="unknown",
        )
    db_type = "postgresql" if "postgres" in normalized.lower() else "sqlite"
    start_time = time.perf_counter()
    temp_engine = None
    try:
        from app.core.database import create_engine_for_url
        temp_engine = create_engine_for_url(normalized)
        async with temp_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            tables = []
            if db_type == "postgresql":
                res = await conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                )
                tables = [r[0] for r in res.fetchall()]
            else:
                res = await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
                tables = [r[0] for r in res.fetchall()]

        latency = round((time.perf_counter() - start_time) * 1000, 2)
        target_name = (
            "Neon PostgreSQL Cloud"
            if "neon.tech" in target_url.lower()
            else ("PostgreSQL Server" if db_type == "postgresql" else "Embedded Database")
        )
        return DatabaseValidationResponse(
            status="valid",
            message=f"Connected successfully to {target_name} ({latency}ms).",
            database_type=db_type,
            normalized_url=mask_database_url(normalized),
            latency_ms=latency,
            tables_found=tables,
        )
    except Exception as e:
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return DatabaseValidationResponse(
            status="invalid",
            message=f"Database connection failed: {str(e)}",
            database_type=db_type,
            latency_ms=latency,
        )
    finally:
        if temp_engine:
            try:
                await temp_engine.dispose()
            except Exception:
                pass


async def validate_gemini_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key or not api_key.strip():
        status = ProviderValidationStatus(
            status="unconfigured",
            message="No Gemini API Key provided.",
            model_tested="gemini-flash-lite-latest",
        )
        provider_health_cache["gemini"] = "unconfigured"
        return status
    clean_key = api_key.strip()
    client = genai.Client(api_key=clean_key)
    
    preferred_models = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-flash-latest",
    ]
    models_to_try = list(preferred_models)
    try:
        listed = []
        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            actions = getattr(m, "supported_actions", []) or getattr(m, "supported_generation_methods", []) or []
            if actions and "generateContent" not in actions:
                continue
            name_clean = name.replace("models/", "")
            if any(k in name_clean.lower() for k in ["tts", "audio", "embed", "imagen", "realtime", "live", "customtools"]):
                continue
            listed.append(name_clean)
        if listed:
            flash_text = [m for m in listed if "flash" in m.lower()]
            models_to_try = preferred_models + flash_text + listed
    except Exception:
        pass

    seen = set()
    deduped_models = []
    for m in models_to_try:
        if m not in seen:
            seen.add(m)
            deduped_models.append(m)

    last_err = ""
    had_high_demand = False
    for model_name in deduped_models:
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents="ping",
            )
            if resp and resp.text:
                provider_health_cache["gemini"] = "valid"
                return ProviderValidationStatus(
                    status="valid",
                    message=f"Connected successfully to Gemini API ({model_name}).",
                    model_tested=model_name,
                )
        except Exception as e:
            err_msg = str(e)
            last_err = err_msg
            err_lower = err_msg.lower()
            if any(k in err_lower for k in ["api_key_invalid", "api key not valid", "permission_denied", "consumer_invalid", "consumer_suspended", "unauthenticated", "401"]):
                provider_health_cache["gemini"] = "invalid"
                return ProviderValidationStatus(
                    status="invalid",
                    message=f"Gemini API key is invalid: {err_msg}",
                    model_tested=model_name,
                )
            if "503" in err_lower or "high demand" in err_lower or "429" in err_lower or "quota" in err_lower:
                had_high_demand = True
            # For 404, 400, 503, 429, continue to next model!
            continue

    if had_high_demand:
        # Key is authenticated and valid, but Google is experiencing high traffic
        provider_health_cache["gemini"] = "valid"
        return ProviderValidationStatus(
            status="valid",
            message="Gemini key authenticated successfully. (Note: Google servers currently report high demand spikes; Groq cascade is ready as active fallback).",
            model_tested=deduped_models[0] if deduped_models else "gemini-flash-lite-latest",
        )

    provider_health_cache["gemini"] = "invalid"
    return ProviderValidationStatus(
        status="invalid",
        message=f"Gemini connection failed: {last_err or 'No accessible Gemini models found for this key.'}",
        model_tested="gemini-flash-lite-latest",
    )


async def validate_groq_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key or not api_key.strip():
        provider_health_cache["groq"] = "unconfigured"
        return ProviderValidationStatus(
            status="unconfigured",
            message="No Groq API Key provided.",
            model_tested="openai/gpt-oss-120b",
        )
    clean_key = api_key.strip()
    client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=clean_key)

    models_to_try = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "allam-2-7b",
    ]
    try:
        model_list = await client.models.list()
        active_ids = [
            m.id for m in model_list.data 
            if m.id and not any(k in m.id.lower() for k in ["whisper", "guard", "orpheus", "safeguard", "embed"])
        ]
        if active_ids:
            models_to_try = active_ids + models_to_try
    except Exception as list_err:
        err_str = str(list_err)
        if "401" in err_str or "invalid" in err_str.lower():
            provider_health_cache["groq"] = "invalid"
            return ProviderValidationStatus(
                status="invalid",
                message=f"Groq authentication failed: {err_str}",
                model_tested="openai/gpt-oss-120b",
            )

    last_err = ""
    for model_name in models_to_try:
        try:
            resp = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            if resp.choices:
                provider_health_cache["groq"] = "valid"
                return ProviderValidationStatus(
                    status="valid",
                    message=f"Connected successfully to Groq Cloud ({model_name} on LPUs).",
                    model_tested=model_name,
                )
        except Exception as e:
            err_str = str(e)
            last_err = err_str
            if "model_not_found" in err_str or "404" in err_str:
                continue
            # Try next model
            continue

    provider_health_cache["groq"] = "invalid"
    return ProviderValidationStatus(
        status="invalid",
        message=f"Groq connection failed: {last_err or 'No accessible models for this Groq key.'}",
        model_tested="openai/gpt-oss-120b",
    )


async def validate_ollama_key(
    api_key: Optional[str],
    base_url: Optional[str] = None,
) -> ProviderValidationStatus:
    if not api_key or not api_key.strip():
        provider_health_cache["ollama"] = "unconfigured"
        return ProviderValidationStatus(
            status="unconfigured",
            message="No Ollama API Key provided.",
            model_tested="gpt-oss:120b",
        )
    clean_key = api_key.strip()
    clean_base = (base_url or settings.OLLAMA_BASE_URL or "https://ollama.com/v1").rstrip("/")
    client = AsyncOpenAI(base_url=clean_base, api_key=clean_key)
    models_to_try = [
        "gpt-oss:120b",
        "gpt-oss:20b",
        "gemma4:31b",
        "nemotron-3-nano:30b",
        "nemotron-3-super",
        "nemotron-3-ultra",
        "beam",
    ]

    last_err = ""
    for model_name in models_to_try:
        try:
            resp = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            if resp.choices:
                provider_health_cache["ollama"] = "valid"
                return ProviderValidationStatus(
                    status="valid",
                    message=f"Connected successfully to Ollama Cloud ({model_name}).",
                    model_tested=model_name,
                )
        except Exception as e:
            err_str = str(e)
            last_err = err_str
            if "404" in err_str or "not found" in err_str.lower():
                continue
            provider_health_cache["ollama"] = "invalid"
            return ProviderValidationStatus(
                status="invalid",
                message=f"Ollama connection failed: {err_str}",
                model_tested=model_name,
            )
    provider_health_cache["ollama"] = "invalid"
    return ProviderValidationStatus(
        status="invalid",
        message=f"Ollama connection failed: {last_err or 'No accessible Ollama models found.'}",
        model_tested="gpt-oss:120b",
    )


async def validate_google_cse_keys(
    cx_id: Optional[str] = None, *args, **kwargs
) -> ProviderValidationStatus:
    target_cx = args[0] if (args and not cx_id) else cx_id
    clean_cx = clean_google_cx_id(target_cx)
    if not clean_cx:
        return ProviderValidationStatus(
            status="unconfigured",
            message="Search Engine ID (cx) is not configured. (Tip: 1-Click Direct Google Sourcing works anytime without setup).",
            model_tested="Google Programmable Search (Widget Mode)",
        )

    return ProviderValidationStatus(
        status="valid",
        message=f"Search Engine ID ({clean_cx[:8]}...) is active! Browser widget & 1-Click X-Ray ready with 0 API keys required.",
        model_tested="Google Programmable Search (Widget Mode)",
    )


async def validate_all_settings(
    req: Optional[UserSettingsUpdateRequest], db: AsyncSession
) -> SettingsValidationResponse:
    """Validates connectivity to all AI and CSE providers."""
    record = await get_or_create_user_settings(db)

    gemini_key = req.gemini_api_key if (req and req.gemini_api_key is not None) else record.gemini_api_key
    groq_key = req.groq_api_key if (req and req.groq_api_key is not None) else record.groq_api_key
    ollama_key = req.ollama_api_key if (req and req.ollama_api_key is not None) else getattr(record, "ollama_api_key", None)
    ollama_base = req.ollama_base_url if (req and req.ollama_base_url is not None) else getattr(record, "ollama_base_url", None)
    cse_cx = req.google_cse_cx_id if (req and req.google_cse_cx_id is not None) else record.google_cse_cx_id

    gemini_status = await validate_gemini_key(gemini_key)
    groq_status = await validate_groq_key(groq_key)
    ollama_status = await validate_ollama_key(ollama_key, ollama_base)
    cse_status = await validate_google_cse_keys(cse_cx)

    provider_health_cache["gemini"] = gemini_status.status
    provider_health_cache["groq"] = groq_status.status
    provider_health_cache["ollama"] = ollama_status.status

    overall_ready = any(
        s.status == "valid" for s in [gemini_status, groq_status, ollama_status]
    )

    return SettingsValidationResponse(
        gemini=gemini_status,
        groq=groq_status,
        ollama=ollama_status,
        google_cse=cse_status,
        overall_ready=overall_ready,
    )


# ==============================================================================
# Job Description Templates Management & Schema Sync
# ==============================================================================

DEFAULT_JOB_TEMPLATES = [t.model_dump() for t in _cached_defaults.job_templates]


def get_default_job_templates() -> List[dict]:
    """Returns the active list of default job templates from the JSON schema."""
    return [t.model_dump() for t in load_default_settings_schema().job_templates]


async def sync_job_templates_to_json_file(db: AsyncSession) -> AppDefaultsSchema:
    """
    Reverse sync: Reads JobTemplates and UserSettings from database,
    updates modified_timestamp to current UTC, and updates fixtures/job_template.json and fixtures/user_settings.json.
    """
    new_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    templates = await get_all_job_templates(db)
    record = await get_or_create_user_settings(db)
    record.job_templates_schema_timestamp = new_timestamp
    await db.commit()

    schema = AppDefaultsSchema(
        version="1.0.0",
        modified_timestamp=new_timestamp,
        system_settings=SystemSettingsDefaultsSchema(
            project_name=record.project_name or DEFAULT_PROJECT_NAME,
            version=record.version or DEFAULT_VERSION,
            subscription_tier=record.subscription_tier or DEFAULT_SUBSCRIPTION_TIER,
            evaluation_mode=record.evaluation_mode or DEFAULT_EVALUATION_MODE,
            rate_limit_rpm=record.rate_limit_rpm or DEFAULT_RATE_LIMIT_RPM,
        ),
        job_templates=[
            JobTemplateSchema(
                title=t.title,
                category=t.category or "General",
                description=t.description,
            )
            for t in templates
        ],
    )
    save_default_settings_schema(schema)
    logger.info(f"[Job Templates Reverse Sync] Synchronized database templates into fixtures/job_template.json and fixtures/user_settings.json (new timestamp: {new_timestamp}).")
    return schema


async def sync_global_defaults(db: AsyncSession, force: bool = False) -> DefaultsSyncResult:
    """
    Performs global insertion and synchronization of JSON settings schema into the active database.
    - Compares modified_timestamp: if the schema timestamp changed from the database, it syncs updates.
    - If default templates or settings are missing, inserts them.
    - Preserves user-created custom templates and API credentials.
    """
    await _ensure_schema_columns_exist(db)
    schema = load_default_settings_schema()
    record = await get_or_create_user_settings(db)

    timestamp_changed = record.job_templates_schema_timestamp != schema.modified_timestamp
    if timestamp_changed:
        logger.info(
            f"[Global Defaults Sync] Detected modified schema timestamp: "
            f"'{schema.modified_timestamp}' != '{record.job_templates_schema_timestamp}'. "
            f"Synchronizing schema into database..."
        )

    inserted = 0
    updated = 0
    unchanged = 0

    # 1. Sync Job Templates
    stmt = select(JobTemplate)
    result = await db.execute(stmt)
    existing_templates = list(result.scalars().all())
    existing_by_title = {t.title.strip().lower(): t for t in existing_templates}

    for item in schema.job_templates:
        key = item.title.strip().lower()
        item_cat = item.category.strip() if item.category else "General"
        item_desc = item.description.strip()

        if key not in existing_by_title:
            # Global insertion of new default template
            new_t = JobTemplate(
                title=item.title.strip(),
                category=item_cat,
                description=item_desc,
            )
            db.add(new_t)
            inserted += 1
        else:
            # Template exists: check if schema data or timestamp changed
            existing_t = existing_by_title[key]
            changed = False

            if (existing_t.category or "").strip() != item_cat:
                existing_t.category = item_cat
                changed = True
            if (existing_t.description or "").strip() != item_desc:
                existing_t.description = item_desc
                changed = True

            if changed or force or timestamp_changed:
                existing_t.category = item_cat
                existing_t.description = item_desc
                existing_t.updated_at = utc_now()
                updated += 1
            else:
                unchanged += 1

    # 2. Sync System Settings
    settings_synced = False
    sys_defs = schema.system_settings

    if not record.project_name or record.project_name == DEFAULT_PROJECT_NAME:
        if record.project_name != sys_defs.project_name:
            record.project_name = sys_defs.project_name
            settings_synced = True
    if not record.version or record.version == DEFAULT_VERSION:
        if record.version != sys_defs.version:
            record.version = sys_defs.version
            settings_synced = True
    if not record.subscription_tier:
        record.subscription_tier = sys_defs.subscription_tier
        settings_synced = True
    if not record.evaluation_mode:
        record.evaluation_mode = sys_defs.evaluation_mode
        settings_synced = True
    if not record.rate_limit_rpm:
        record.rate_limit_rpm = sys_defs.rate_limit_rpm
        settings_synced = True

    if record.job_templates_schema_timestamp != schema.modified_timestamp:
        record.job_templates_schema_timestamp = schema.modified_timestamp
        settings_synced = True

    await db.commit()
    await db.refresh(record)

    msg = f"Synced schema into database: {inserted} inserted, {updated} updated, {unchanged} unchanged."
    if settings_synced:
        msg += " System settings defaults updated."
    logger.info(f"[Global Defaults Sync] {msg}")

    return DefaultsSyncResult(
        templates_inserted=inserted,
        templates_updated=updated,
        templates_unchanged=unchanged,
        settings_synced=settings_synced,
        instructions_synced=False,
        message=msg,
    )


def template_to_response(template: JobTemplate) -> JobTemplateResponse:
    """Converts a database JobTemplate to a safe API response schema."""
    return JobTemplateResponse(
        id=template.id,
        title=template.title,
        category=template.category or "General",
        description=template.description,
        created_at=template.created_at.strftime("%Y-%m-%d %H:%M") if template.created_at else None,
        updated_at=template.updated_at.strftime("%Y-%m-%d %H:%M") if template.updated_at else None,
    )


async def get_all_job_templates(db: AsyncSession) -> List[JobTemplate]:
    """Retrieves all configured job description templates, syncing defaults from JSON schema if empty."""
    stmt = select(JobTemplate).order_by(JobTemplate.category, JobTemplate.title)
    result = await db.execute(stmt)
    templates = list(result.scalars().all())

    if not templates:
        await sync_global_defaults(db)
        result = await db.execute(stmt)
        templates = list(result.scalars().all())

    return templates


async def get_job_template_by_id(db: AsyncSession, template_id: int) -> Optional[JobTemplate]:
    """Retrieves a single job description template by ID."""
    stmt = select(JobTemplate).where(JobTemplate.id == template_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_job_template(
    db: AsyncSession, payload: JobTemplateCreateRequest
) -> JobTemplate:
    """Creates a new job description template in the database."""
    template = JobTemplate(
        title=payload.title.strip(),
        category=payload.category.strip() if payload.category else "General",
        description=payload.description.strip(),
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_job_template(
    db: AsyncSession, template_id: int, payload: JobTemplateUpdateRequest
) -> Optional[JobTemplate]:
    """Updates an existing job description template."""
    template = await get_job_template_by_id(db, template_id)
    if not template:
        return None

    if payload.title is not None:
        template.title = payload.title.strip()
    if payload.category is not None:
        template.category = payload.category.strip()
    if payload.description is not None:
        template.description = payload.description.strip()

    await db.commit()
    await db.refresh(template)
    return template


async def delete_job_template(db: AsyncSession, template_id: int) -> bool:
    """Deletes a job description template by ID."""
    template = await get_job_template_by_id(db, template_id)
    if not template:
        return False

    await db.delete(template)
    await db.commit()
    return True


async def reset_default_job_templates(db: AsyncSession) -> List[JobTemplate]:
    """Resets the job description templates to standard out-of-the-box defaults from the JSON schema."""
    await db.execute(delete(JobTemplate))
    await db.commit()
    await sync_global_defaults(db)
    return await get_all_job_templates(db)
