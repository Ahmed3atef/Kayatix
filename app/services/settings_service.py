import logging
import re
from typing import List, Optional
import httpx
from google import genai
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.domain import JobTemplate, UserSettings
from app.schemas.payloads import (
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
DEFAULT_EVALUATION_MODE = "hybrid"
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
        evaluation_mode=record.evaluation_mode or DEFAULT_EVALUATION_MODE,
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
