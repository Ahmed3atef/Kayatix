from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.core.config import settings
from app.schemas.payloads import UserSettingsUpdateRequest
from app.services.settings_service import (
    get_settings_summary,
    update_user_settings,
    validate_all_settings,
)




@pytest.mark.asyncio
async def test_get_and_update_settings_in_database(db_session):
    """Verifies that API keys and subscription tiers persist to SQLite database."""
    initial = await get_settings_summary(db_session)
    assert initial.subscription_tier in ("standard", "free")


    # Update settings
    update_req = UserSettingsUpdateRequest(
        gemini_api_key="new_gemini_key",
        groq_api_key="new_groq_key",
        subscription_tier="pro",
        rate_limit_rpm=30,
    )
    updated = await update_user_settings(update_req, db_session)

    assert updated.gemini_api_key_configured is True
    assert updated.groq_api_key_configured is True
    assert updated.subscription_tier == "pro"
    assert updated.rate_limit_rpm == 30

    # Verify that in-memory runtime settings were updated
    assert settings.GEMINI_API_KEY == "new_gemini_key"
    assert settings.GROQ_API_KEY == "new_groq_key"


@pytest.mark.asyncio
async def test_update_raw_env_content(db_session):
    """Verifies that editing .env directly parses keys into the database record."""
    raw_env = (
        'PROJECT_NAME="Custom HR Copilot"\n'
        'GEMINI_API_KEY="AIzaSyTest123"\n'
        'SUBSCRIPTION_TIER="enterprise"\n'
        'RATE_LIMIT_RPM=45\n'
    )

    update_req = UserSettingsUpdateRequest(env_content=raw_env)
    res = await update_user_settings(update_req, db_session)

    assert res.gemini_api_key_configured is True
    assert res.subscription_tier == "enterprise"
    assert res.rate_limit_rpm == 45
    assert settings.GEMINI_API_KEY == "AIzaSyTest123"


@pytest.mark.asyncio
async def test_validate_all_settings_success(db_session):
    """Verifies live validation logic for AI providers and Google CSE."""
    with (
        patch("app.services.settings_service.validate_gemini_key", new_callable=AsyncMock) as m_gemini,
        patch("app.services.settings_service.validate_groq_key", new_callable=AsyncMock) as m_groq,
        patch("app.services.settings_service.validate_openrouter_key", new_callable=AsyncMock) as m_openrouter,
        patch("app.services.settings_service.validate_google_cse_keys", new_callable=AsyncMock) as m_cse,
    ):
        from app.schemas.payloads import ProviderValidationStatus

        m_gemini.return_value = ProviderValidationStatus(
            status="valid", message="Connected", model_tested="gemini-2.5-flash"
        )
        m_groq.return_value = ProviderValidationStatus(
            status="valid", message="Connected", model_tested="llama-3.3-70b-versatile"
        )
        m_openrouter.return_value = ProviderValidationStatus(
            status="unconfigured", message="No key", model_tested="meta-llama/llama-3.1-8b-instruct:free"
        )
        m_cse.return_value = ProviderValidationStatus(
            status="valid", message="Connected", model_tested="Google CSE"
        )

        resp = await validate_all_settings(None, db_session)
        assert resp.overall_ready is True
        assert resp.gemini.status == "valid"
        assert resp.groq.status == "valid"


def test_clean_google_cx_id():
    """Verifies that script tags and raw URLs are stripped to extract just the cx ID."""
    from app.services.settings_service import clean_google_cx_id

    # Raw ID
    assert clean_google_cx_id("c5c6e8ce160ff411e") == "c5c6e8ce160ff411e"
    # Script tag
    script_snippet = '<script async src="https://cse.google.com/cse.js?cx=c5c6e8ce160ff411e"></script>'
    assert clean_google_cx_id(script_snippet) == "c5c6e8ce160ff411e"
    # Full URL
    url = "https://cse.google.com/cse.js?cx=c5c6e8ce160ff411e"
    assert clean_google_cx_id(url) == "c5c6e8ce160ff411e"
    # None or empty
    assert clean_google_cx_id(None) is None
    assert clean_google_cx_id("") is None


@pytest.mark.asyncio
async def test_validate_google_cse_keys_cx_only():
    """Verifies that providing only Search Engine ID validates as ready for browser sourcing."""
    from app.services.settings_service import validate_google_cse_keys

    result = await validate_google_cse_keys(None, "c5c6e8ce160ff411e")
    assert result.status == "valid"
    assert "Browser widget & 1-Click X-Ray ready" in result.message


def test_normalize_database_url():
    """Verifies that database URLs are properly converted to asyncpg and cleaned of unsupported parameters."""
    from app.core.database import normalize_database_url

    # SQLite
    sqlite_res = normalize_database_url("sqlite:///./hr_copilot.db")
    assert sqlite_res.startswith("sqlite+aiosqlite:///")

    # Standard PostgreSQL link with asyncpg driver injection
    pg_res = normalize_database_url("postgresql://user:pass@localhost:5432/testdb")
    assert pg_res.startswith("postgresql+asyncpg://user:pass@localhost:5432/testdb")

    # Neon PostgreSQL link with sslmode and channel_binding query params
    neon_url = "postgresql://kaya_db_owner:npg_secret@ep-billowing-voice-b5etyv61-pooler.c-7.us-east-2.aws.neon.tech/kaya_db?sslmode=require&channel_binding=require"
    neon_res = normalize_database_url(neon_url)
    assert neon_res.startswith("postgresql+asyncpg://kaya_db_owner:npg_secret@ep-billowing-voice-b5etyv61-pooler.c-7.us-east-2.aws.neon.tech/kaya_db")
    assert "ssl=require" in neon_res
    assert "sslmode" not in neon_res
    assert "channel_binding" not in neon_res


@pytest.mark.asyncio
async def test_validate_database_connection_sqlite():
    """Verifies live validation logic for SQLite database."""
    from app.services.settings_service import validate_database_connection

    # Valid in-memory or file SQLite
    res = await validate_database_connection("sqlite+aiosqlite:///:memory:")
    assert res.status == "valid"
    assert res.database_type == "sqlite"
    assert res.latency_ms is not None

    # Invalid connection string / dialect
    bad_res = await validate_database_connection("unknown_scheme://bad_host/db")
    assert bad_res.status == "invalid"
    assert "Unsupported database scheme" in bad_res.message


@pytest.mark.asyncio
async def test_validate_database_api_endpoint(client):
    """Verifies POST /api/v1/settings/validate-database endpoint."""
    resp = await client.post(
        "/api/v1/settings/validate-database",
        json={"database_url": "sqlite+aiosqlite:///:memory:"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "valid"
    assert data["database_type"] == "sqlite"
    assert "latency_ms" in data


@pytest.mark.asyncio
async def test_settings_page_renders_database_engine_section(client):
    """Verifies that the Settings UI displays database engine switcher and controls."""
    resp = await client.get("/settings")
    assert resp.status_code == 200
    html = resp.text
    assert "Database Engine Backend" in html
    assert "id=\"databaseUrlInput\"" in html
    assert "id=\"testDbConnBtn\"" in html
    assert "id=\"dbChoiceSqlite\"" in html
    assert "id=\"dbChoicePostgres\"" in html

