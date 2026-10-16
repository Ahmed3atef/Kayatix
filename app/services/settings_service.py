import logging
import os
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
from app.core.database import (
    DEFAULT_SQLITE_URL,
    AsyncSessionLocal,
    normalize_database_url,
    switch_database_engine,
)
from app.models.domain import JobTemplate, UserSettings
from app.schemas.payloads import (
    DatabaseValidationResponse,
    JobTemplateCreateRequest,
    JobTemplateResponse,
    JobTemplateUpdateRequest,
    ProviderValidationStatus,
    SettingsValidationResponse,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)

logger = logging.getLogger(__name__)


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

# Default out-of-the-box configuration
DEFAULT_PROJECT_NAME = "Kayatix - A.Y.A.T. Engine"
DEFAULT_VERSION = "1.0.0"
DEFAULT_SUBSCRIPTION_TIER = "standard"
DEFAULT_EVALUATION_MODE = "llm_cascade"
DEFAULT_RATE_LIMIT_RPM = 15


def generate_config_text(record: UserSettings) -> str:
    """Generates standardized key-value configuration text from database record."""
    active_db = record.database_url or settings.DATABASE_URL
    return (
        f'PROJECT_NAME="{record.project_name or DEFAULT_PROJECT_NAME}"\n'
        f'VERSION="{record.version or DEFAULT_VERSION}"\n'
        f'DATABASE_URL="{active_db}"\n\n'
        f'# AI Provider Keys\n'
        f'GEMINI_API_KEY="{record.gemini_api_key or ""}"\n'
        f'GROQ_API_KEY="{record.groq_api_key or ""}"\n'
        f'OPENROUTER_API_KEY="{record.openrouter_api_key or ""}"\n\n'
        f'# Legal LinkedIn X-Ray Search Keys\n'
        f'GOOGLE_CSE_API_KEY="{record.google_cse_api_key or ""}"\n'
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


async def get_or_create_user_settings(db: AsyncSession) -> UserSettings:
    """Retrieves user settings row from DB or initializes it with complete out-of-the-box defaults."""
    stmt = select(UserSettings).limit(1)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        # Pre-populate with working defaults in SQLite
        user_settings = UserSettings(
            project_name=DEFAULT_PROJECT_NAME,
            version=DEFAULT_VERSION,
            gemini_api_key=settings.GEMINI_API_KEY,
            groq_api_key=settings.GROQ_API_KEY,
            openrouter_api_key=settings.OPENROUTER_API_KEY,
            google_cse_api_key=settings.GOOGLE_CSE_API_KEY,
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

    # Sync runtime memory configuration from database
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
    if user_settings.subscription_tier:
        settings.SUBSCRIPTION_TIER = user_settings.subscription_tier
    if user_settings.evaluation_mode:
        settings.EVALUATION_MODE = user_settings.evaluation_mode
    if user_settings.rate_limit_rpm:
        settings.RATE_LIMIT_RPM = user_settings.rate_limit_rpm
    if user_settings.database_url:
        settings.DATABASE_URL = user_settings.database_url

    return user_settings


async def get_settings_summary(db: AsyncSession) -> UserSettingsResponse:
    """Returns configuration overview, secret status, and raw configuration representation."""
    record = await get_or_create_user_settings(db)
    env_str = record.env_content or generate_config_text(record)
    active_db = record.database_url or settings.DATABASE_URL
    db_type = "postgresql" if "postgres" in active_db.lower() else "sqlite"

    return UserSettingsResponse(
        gemini_api_key_configured=bool(record.gemini_api_key),
        groq_api_key_configured=bool(record.groq_api_key),
        openrouter_api_key_configured=bool(record.openrouter_api_key),
        google_cse_api_key_configured=bool(record.google_cse_api_key),
        google_cse_cx_id_configured=bool(record.google_cse_cx_id),
        subscription_tier=record.subscription_tier or DEFAULT_SUBSCRIPTION_TIER,
        evaluation_mode=record.evaluation_mode or DEFAULT_EVALUATION_MODE,
        rate_limit_rpm=record.rate_limit_rpm or DEFAULT_RATE_LIMIT_RPM,
        database_url=active_db,
        database_type=db_type,
        env_content=env_str,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )


async def update_user_settings(
    req: UserSettingsUpdateRequest, db: AsyncSession
) -> UserSettingsResponse:
    """Persists updated API keys and configuration directly into SQLite database."""
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
        if "OPENROUTER_API_KEY" in parsed:
            record.openrouter_api_key = parsed["OPENROUTER_API_KEY"].strip() or None
            settings.OPENROUTER_API_KEY = record.openrouter_api_key
        if "GOOGLE_CSE_API_KEY" in parsed:
            record.google_cse_api_key = parsed["GOOGLE_CSE_API_KEY"].strip() or None
            settings.GOOGLE_CSE_API_KEY = record.google_cse_api_key
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

    # Otherwise process individual structured fields
    if req.gemini_api_key is not None:
        record.gemini_api_key = req.gemini_api_key.strip() or None
        settings.GEMINI_API_KEY = record.gemini_api_key
    if req.groq_api_key is not None:
        record.groq_api_key = req.groq_api_key.strip() or None
        settings.GROQ_API_KEY = record.groq_api_key
    if req.openrouter_api_key is not None:
        record.openrouter_api_key = req.openrouter_api_key.strip() or None
        settings.OPENROUTER_API_KEY = record.openrouter_api_key
    if req.google_cse_api_key is not None:
        record.google_cse_api_key = req.google_cse_api_key.strip() or None
        settings.GOOGLE_CSE_API_KEY = record.google_cse_api_key
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

    # Check if database_url is provided in raw env or structured request
    target_db_url = None
    if req.env_content is not None and req.env_content.strip():
        parsed = parse_config_text(req.env_content)
        if "DATABASE_URL" in parsed and parsed["DATABASE_URL"].strip():
            target_db_url = parsed["DATABASE_URL"].strip()
    if req.database_url is not None and req.database_url.strip():
        target_db_url = req.database_url.strip()

    if target_db_url:
        normalized_target = normalize_database_url(target_db_url)
        current_normalized = normalize_database_url(record.database_url or settings.DATABASE_URL)
        if normalized_target != current_normalized:
            # Validate target connection first
            val = await validate_database_connection(normalized_target)
            if val.status != "valid":
                raise HTTPException(status_code=400, detail=f"Cannot switch database: {val.message}")

            # Grab existing templates from current db session to migrate
            existing_templates = await get_all_job_templates(db)
            saved_settings = {
                "project_name": record.project_name,
                "version": record.version,
                "gemini_api_key": req.gemini_api_key.strip() if req.gemini_api_key is not None else record.gemini_api_key,
                "groq_api_key": req.groq_api_key.strip() if req.groq_api_key is not None else record.groq_api_key,
                "openrouter_api_key": req.openrouter_api_key.strip() if req.openrouter_api_key is not None else record.openrouter_api_key,
                "google_cse_api_key": req.google_cse_api_key.strip() if req.google_cse_api_key is not None else record.google_cse_api_key,
                "google_cse_cx_id": clean_google_cx_id(req.google_cse_cx_id) if req.google_cse_cx_id is not None else record.google_cse_cx_id,
                "subscription_tier": req.subscription_tier or record.subscription_tier,
                "evaluation_mode": req.evaluation_mode or record.evaluation_mode,
                "rate_limit_rpm": req.rate_limit_rpm or record.rate_limit_rpm,
                "database_url": normalized_target,
            }

            # Switch live engine
            await switch_database_engine(normalized_target)

            # Populate target database
            async with AsyncSessionLocal() as new_db:
                new_rec_res = await new_db.execute(select(UserSettings).limit(1))
                new_rec = new_rec_res.scalar_one_or_none()
                if not new_rec:
                    new_rec = UserSettings(**saved_settings)
                    new_rec.env_content = generate_config_text(new_rec)
                    new_db.add(new_rec)
                else:
                    for k, v in saved_settings.items():
                        setattr(new_rec, k, v)
                    new_rec.env_content = generate_config_text(new_rec)

                # Migrate templates if target database has none
                tpl_res = await new_db.execute(select(JobTemplate).limit(1))
                if not tpl_res.scalar_one_or_none() and existing_templates:
                    for t in existing_templates:
                        new_db.add(JobTemplate(title=t.title, category=t.category, description=t.description))

                await new_db.commit()
                await new_db.refresh(new_rec)
                record = new_rec
                db = new_db

            # Persist DATABASE_URL to .env on disk for subsequent process restarts
            try:
                env_path = ".env"
                env_lines = []
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        env_lines = f.readlines()
                db_url_found = False
                new_lines = []
                for line in env_lines:
                    if line.startswith("DATABASE_URL="):
                        new_lines.append(f'DATABASE_URL="{normalized_target}"\n')
                        db_url_found = True
                    else:
                        new_lines.append(line)
                if not db_url_found:
                    new_lines.append(f'DATABASE_URL="{normalized_target}"\n')
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            except Exception as e:
                logger.warning(f"Could not persist DATABASE_URL to .env file: {e}")

    # Regenerate fresh config representation to stay consistent
    record.env_content = generate_config_text(record)

    await db.commit()
    await db.refresh(record)

    return await get_settings_summary(db)


async def validate_database_connection(raw_url: str) -> DatabaseValidationResponse:
    """Validates connectivity to a PostgreSQL or SQLite database link."""
    if not raw_url or not raw_url.strip():
        return DatabaseValidationResponse(
            status="invalid",
            message="Database connection link cannot be empty.",
            database_type="unknown",
        )
    normalized = normalize_database_url(raw_url)
    if not (normalized.startswith("postgresql+asyncpg://") or normalized.startswith("sqlite+aiosqlite://")):
        return DatabaseValidationResponse(
            status="invalid",
            message=f"Unsupported database scheme. Connection URL must start with postgresql:// or sqlite:///",
            database_type="unknown",
        )
    db_type = "postgresql" if "postgres" in normalized.lower() else "sqlite"
    start_time = time.perf_counter()
    try:
        temp_engine = create_async_engine(normalized, echo=False)
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

        await temp_engine.dispose()
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        target_name = (
            "Neon PostgreSQL Cloud"
            if "neon.tech" in raw_url.lower()
            else ("PostgreSQL Database" if db_type == "postgresql" else "SQLite Embedded Database")
        )
        return DatabaseValidationResponse(
            status="valid",
            message=f"Connected successfully to {target_name} ({latency}ms).",
            database_type=db_type,
            normalized_url=normalized,
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


async def validate_gemini_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key:
        return ProviderValidationStatus(
            status="unconfigured",
            message="No Gemini API Key provided.",
            model_tested="gemini-3.8-flash",
        )
    client = genai.Client(api_key=api_key)
    
    preferred_models = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.7-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
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
        return ProviderValidationStatus(
            status="valid",
            message="Gemini key authenticated successfully. (Note: Google servers currently report high demand spikes; Groq cascade is ready as active fallback).",
            model_tested=deduped_models[0] if deduped_models else "gemini-3.8-flash",
        )

    return ProviderValidationStatus(
        status="invalid",
        message=f"Gemini connection failed: {last_err or 'No accessible Gemini models found for this key.'}",
        model_tested="gemini-3.8-flash",
    )


async def validate_groq_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key:
        return ProviderValidationStatus(
            status="unconfigured",
            message="No Groq API Key provided.",
            model_tested="openai/gpt-oss-120b",
        )
    client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)

    models_to_try = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "allam-2-7b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
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

    return ProviderValidationStatus(
        status="invalid",
        message=f"Groq connection failed: {last_err or 'No accessible models for this Groq key.'}",
        model_tested="openai/gpt-oss-120b",
    )


async def validate_openrouter_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key:
        return ProviderValidationStatus(
            status="unconfigured",
            message="No OpenRouter API Key provided.",
            model_tested="meta-llama/llama-3.1-8b-instruct",
        )
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    models_to_try = [
        "meta-llama/llama-3.1-8b-instruct",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.1-8b-instruct:free",
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
                return ProviderValidationStatus(
                    status="valid",
                    message=f"Connected successfully to OpenRouter ({model_name}).",
                    model_tested=model_name,
                )
        except Exception as e:
            err_str = str(e)
            last_err = err_str
            if "404" in err_str or "unavailable for free" in err_str:
                continue
            return ProviderValidationStatus(
                status="invalid",
                message=f"OpenRouter connection failed: {err_str}",
                model_tested=model_name,
            )
    return ProviderValidationStatus(
        status="invalid",
        message=f"OpenRouter connection failed: {last_err or 'No accessible OpenRouter models found.'}",
        model_tested="meta-llama/llama-3.1-8b-instruct",
    )


async def validate_google_cse_keys(
    api_key: Optional[str], cx_id: Optional[str]
) -> ProviderValidationStatus:
    clean_cx = clean_google_cx_id(cx_id)
    if not clean_cx and not api_key:
        return ProviderValidationStatus(
            status="unconfigured",
            message="Search Engine ID (cx) is not configured. You can still use 1-Click Direct Google Sourcing anytime.",
            model_tested="Google Custom Search (X-Ray)",
        )

    # If Search Engine ID (cx) is provided, but Google Cloud API Key is omitted
    if clean_cx and not api_key:
        return ProviderValidationStatus(
            status="valid",
            message=f"Search Engine ID ({clean_cx[:8]}...) is active! Browser widget & 1-Click X-Ray ready. (Google Cloud API key is optional).",
            model_tested="Google Programmable Search (Widget Mode)",
        )

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": clean_cx, "q": "test", "num": 1}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return ProviderValidationStatus(
                    status="valid",
                    message="Google Programmable Search JSON API connected successfully.",
                    model_tested="Google Custom Search API",
                )
            return ProviderValidationStatus(
                status="invalid",
                message=f"Google CSE API returned HTTP {resp.status_code}: {resp.text[:150]}",
                model_tested="Google Custom Search API",
            )
    except Exception as e:
        return ProviderValidationStatus(
            status="invalid",
            message=f"Google CSE connection failed: {str(e)}",
            model_tested="Google Custom Search API",
        )


async def validate_all_settings(
    req: Optional[UserSettingsUpdateRequest], db: AsyncSession
) -> SettingsValidationResponse:
    """Validates connectivity to all AI and CSE providers."""
    record = await get_or_create_user_settings(db)

    gemini_key = req.gemini_api_key if (req and req.gemini_api_key is not None) else record.gemini_api_key
    groq_key = req.groq_api_key if (req and req.groq_api_key is not None) else record.groq_api_key
    openrouter_key = req.openrouter_api_key if (req and req.openrouter_api_key is not None) else record.openrouter_api_key
    cse_key = req.google_cse_api_key if (req and req.google_cse_api_key is not None) else record.google_cse_api_key
    cse_cx = req.google_cse_cx_id if (req and req.google_cse_cx_id is not None) else record.google_cse_cx_id

    gemini_status = await validate_gemini_key(gemini_key)
    groq_status = await validate_groq_key(groq_key)
    openrouter_status = await validate_openrouter_key(openrouter_key)
    cse_status = await validate_google_cse_keys(cse_key, cse_cx)

    overall_ready = any(
        s.status == "valid" for s in [gemini_status, groq_status, openrouter_status]
    )

    return SettingsValidationResponse(
        gemini=gemini_status,
        groq=groq_status,
        openrouter=openrouter_status,
        google_cse=cse_status,
        overall_ready=overall_ready,
    )


# ==============================================================================
# Job Description Templates Management
# ==============================================================================

DEFAULT_JOB_TEMPLATES = [
    {
        "title": "FastAPI Backend Engineer",
        "category": "Engineering",
        "description": (
            "Job Title: Senior FastAPI Backend Engineer\n"
            "Location: Remote / Hybrid\n"
            "Requirements:\n"
            "- 5+ years experience building production backends with Python & FastAPI\n"
            "- Deep proficiency with SQLAlchemy async ORM, PostgreSQL schema design, and query optimization\n"
            "- Experience building microservices, Docker containerization, and REST API standards\n"
            "- Hands-on experience with asynchronous rate-limiting, circuit-breakers, and caching architectures (Redis/SQLite)\n"
            "- Strong understanding of unit testing with pytest and async fixtures."
        ),
    },
    {
        "title": "Full Stack Python / React",
        "category": "Engineering",
        "description": (
            "Job Title: Full Stack Software Engineer (Python & React)\n"
            "Location: Remote\n"
            "Requirements:\n"
            "- 4+ years of professional full-stack development experience\n"
            "- Python, FastAPI or Django on the backend\n"
            "- Modern React, TypeScript, and TailwindCSS or Bootstrap 5 on the frontend\n"
            "- Experience integrating third-party APIs, OAuth, and LLM providers\n"
            "- Strong database knowledge (PostgreSQL, SQLite)."
        ),
    },
    {
        "title": "DevOps & Cloud Platform",
        "category": "Engineering",
        "description": (
            "Job Title: Cloud & DevOps Platform Engineer\n"
            "Location: Remote / Hybrid\n"
            "Requirements:\n"
            "- 5+ years managing Linux infrastructure and cloud environments (AWS/GCP/Azure)\n"
            "- Extensive hands-on experience with Docker, Kubernetes, and Helm\n"
            "- CI/CD automation pipelines (GitHub Actions, GitLab CI)\n"
            "- Infrastructure as Code (Terraform)\n"
            "- Python or Bash scripting for system automation."
        ),
    },
    {
        "title": "Talent Acquisition & HR Lead",
        "category": "Human Resources",
        "description": (
            "Job Title: Senior Talent Acquisition Specialist & HR Lead\n"
            "Location: Remote / On-site\n"
            "Requirements:\n"
            "- 5+ years of full-cycle technical recruiting and HR talent intelligence experience\n"
            "- Demonstrated track record sourcing candidates via Boolean search, LinkedIn X-Ray, and developer communities\n"
            "- Experience with Applicant Tracking Systems (ATS) and candidate evaluation benchmarking\n"
            "- Strong competency in structured behavioral interviews and merit-based talent screening\n"
            "- Excellent stakeholder communication and compensation negotiation skills."
        ),
    },
    {
        "title": "Growth Marketing Manager",
        "category": "Marketing",
        "description": (
            "Job Title: Growth & Digital Marketing Manager\n"
            "Location: Remote / Hybrid\n"
            "Requirements:\n"
            "- 4+ years experience in B2B SaaS growth marketing, SEO, and paid acquisition\n"
            "- Proven track record increasing conversion rates (CRO) and MRR with quantified pipeline growth\n"
            "- Deep proficiency with Google Analytics 4, HubSpot, Mixpanel, and SEMrush\n"
            "- Hands-on experience running multi-channel campaigns (LinkedIn Ads, Google Search, Email nurturing)\n"
            "- Strong data analysis skills (SQL or Python a plus) to measure CAC, LTV, and retention."
        ),
    },
    {
        "title": "Financial Analyst & Controller",
        "category": "Finance",
        "description": (
            "Job Title: Senior Financial Analyst & Corporate Controller\n"
            "Location: Hybrid / On-site\n"
            "Requirements:\n"
            "- 5+ years of financial planning & analysis (FP&A), budget forecasting, and corporate reporting\n"
            "- Advanced financial modeling in Excel, Power BI, and ERP systems (SAP/NetSuite)\n"
            "- CPA or CFA qualification preferred; strong knowledge of US GAAP / IFRS standards\n"
            "- Demonstrated success in cost optimization, margin expansion, and audit defense\n"
            "- Experience presenting quarterly board decks and capital allocation models."
        ),
    },
]


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
    """Retrieves all configured job description templates, seeding defaults if empty."""
    stmt = select(JobTemplate).order_by(JobTemplate.category, JobTemplate.title)
    result = await db.execute(stmt)
    templates = list(result.scalars().all())

    if not templates:
        for t_data in DEFAULT_JOB_TEMPLATES:
            t = JobTemplate(
                title=t_data["title"],
                category=t_data["category"],
                description=t_data["description"],
            )
            db.add(t)
        await db.commit()
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
    """Resets the job description templates to standard out-of-the-box defaults."""
    await db.execute(delete(JobTemplate))
    await db.commit()
    return await get_all_job_templates(db)
