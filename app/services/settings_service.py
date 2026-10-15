import logging
from typing import Optional
import httpx
from google import genai
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.domain import UserSettings
from app.schemas.payloads import (
    ProviderValidationStatus,
    SettingsValidationResponse,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)

logger = logging.getLogger(__name__)

# Default out-of-the-box configuration
DEFAULT_PROJECT_NAME = "Kayatix - A.Y.A.T. Engine"
DEFAULT_VERSION = "1.0.0"
DEFAULT_SUBSCRIPTION_TIER = "standard"
DEFAULT_RATE_LIMIT_RPM = 15


def generate_config_text(record: UserSettings) -> str:
    """Generates standardized key-value configuration text from database record."""
    return (
        f'PROJECT_NAME="{record.project_name or DEFAULT_PROJECT_NAME}"\n'
        f'VERSION="{record.version or DEFAULT_VERSION}"\n'
        f'DATABASE_URL="{settings.DATABASE_URL}"\n\n'
        f'# AI Provider Keys\n'
        f'GEMINI_API_KEY="{record.gemini_api_key or ""}"\n'
        f'GROQ_API_KEY="{record.groq_api_key or ""}"\n'
        f'OPENROUTER_API_KEY="{record.openrouter_api_key or ""}"\n\n'
        f'# Legal LinkedIn X-Ray Search Keys\n'
        f'GOOGLE_CSE_API_KEY="{record.google_cse_api_key or ""}"\n'
        f'GOOGLE_CSE_CX_ID="{record.google_cse_cx_id or ""}"\n\n'
        f'# Subscription & Rate Limits\n'
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
            rate_limit_rpm=DEFAULT_RATE_LIMIT_RPM,
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
    if user_settings.rate_limit_rpm:
        settings.RATE_LIMIT_RPM = user_settings.rate_limit_rpm

    return user_settings


async def get_settings_summary(db: AsyncSession) -> UserSettingsResponse:
    """Returns configuration overview, secret status, and raw configuration representation."""
    record = await get_or_create_user_settings(db)
    env_str = record.env_content or generate_config_text(record)

    return UserSettingsResponse(
        gemini_api_key_configured=bool(record.gemini_api_key),
        groq_api_key_configured=bool(record.groq_api_key),
        openrouter_api_key_configured=bool(record.openrouter_api_key),
        google_cse_api_key_configured=bool(record.google_cse_api_key),
        google_cse_cx_id_configured=bool(record.google_cse_cx_id),
        subscription_tier=record.subscription_tier or DEFAULT_SUBSCRIPTION_TIER,
        rate_limit_rpm=record.rate_limit_rpm or DEFAULT_RATE_LIMIT_RPM,
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
            record.google_cse_cx_id = parsed["GOOGLE_CSE_CX_ID"].strip() or None
            settings.GOOGLE_CSE_CX_ID = record.google_cse_cx_id
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
        record.google_cse_cx_id = req.google_cse_cx_id.strip() or None
        settings.GOOGLE_CSE_CX_ID = record.google_cse_cx_id
    if req.subscription_tier is not None:
        record.subscription_tier = req.subscription_tier
        settings.SUBSCRIPTION_TIER = record.subscription_tier
    if req.rate_limit_rpm is not None:
        record.rate_limit_rpm = req.rate_limit_rpm
        settings.RATE_LIMIT_RPM = record.rate_limit_rpm

    # Regenerate fresh config representation to stay consistent
    record.env_content = generate_config_text(record)

    await db.commit()
    await db.refresh(record)

    return await get_settings_summary(db)


async def validate_gemini_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key:
        return ProviderValidationStatus(
            status="unconfigured",
            message="No Gemini API Key provided.",
            model_tested="gemini-2.5-flash",
        )
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="ping",
        )
        if resp and resp.text:
            return ProviderValidationStatus(
                status="valid",
                message="Connected successfully to Gemini 2.5 Flash API.",
                model_tested="gemini-2.5-flash",
            )
        return ProviderValidationStatus(
            status="invalid",
            message="Received empty response from Gemini API.",
            model_tested="gemini-2.5-flash",
        )
    except Exception as e:
        return ProviderValidationStatus(
            status="invalid",
            message=f"Gemini connection failed: {str(e)}",
            model_tested="gemini-2.5-flash",
        )


async def validate_groq_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key:
        return ProviderValidationStatus(
            status="unconfigured",
            message="No Groq API Key provided.",
            model_tested="llama-3.3-70b-versatile",
        )
    try:
        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
        resp = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        if resp.choices:
            return ProviderValidationStatus(
                status="valid",
                message="Connected successfully to Groq Cloud (LPU accelerated).",
                model_tested="llama-3.3-70b-versatile",
            )
        return ProviderValidationStatus(
            status="invalid",
            message="No choices returned from Groq API.",
            model_tested="llama-3.3-70b-versatile",
        )
    except Exception as e:
        return ProviderValidationStatus(
            status="invalid",
            message=f"Groq connection failed: {str(e)}",
            model_tested="llama-3.3-70b-versatile",
        )


async def validate_openrouter_key(api_key: Optional[str]) -> ProviderValidationStatus:
    if not api_key:
        return ProviderValidationStatus(
            status="unconfigured",
            message="No OpenRouter API Key provided.",
            model_tested="meta-llama/llama-3.1-8b-instruct:free",
        )
    try:
        client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        resp = await client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct:free",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        if resp.choices:
            return ProviderValidationStatus(
                status="valid",
                message="Connected successfully to OpenRouter Free Pool.",
                model_tested="meta-llama/llama-3.1-8b-instruct:free",
            )
        return ProviderValidationStatus(
            status="invalid",
            message="No choices returned from OpenRouter API.",
            model_tested="meta-llama/llama-3.1-8b-instruct:free",
        )
    except Exception as e:
        return ProviderValidationStatus(
            status="invalid",
            message=f"OpenRouter connection failed: {str(e)}",
            model_tested="meta-llama/llama-3.1-8b-instruct:free",
        )


async def validate_google_cse_keys(
    api_key: Optional[str], cx_id: Optional[str]
) -> ProviderValidationStatus:
    if not api_key or not cx_id:
        return ProviderValidationStatus(
            status="unconfigured",
            message="Google CSE API Key or Search Engine ID (cx) is missing.",
            model_tested="Google Custom Search API",
        )
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cx_id, "q": "test", "num": 1}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return ProviderValidationStatus(
                    status="valid",
                    message="Google Programmable Search Engine connected successfully.",
                    model_tested="Google Custom Search API",
                )
            return ProviderValidationStatus(
                status="invalid",
                message=f"Google CSE error (HTTP {resp.status_code}): {resp.text[:150]}",
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
