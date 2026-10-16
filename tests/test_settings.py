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
        ollama_api_key="new_ollama_key",
        subscription_tier="pro",
        rate_limit_rpm=30,
    )
    updated = await update_user_settings(update_req, db_session)

    assert updated.gemini_api_key_configured is True
    assert updated.groq_api_key_configured is True
    assert updated.ollama_api_key_configured is True
    assert updated.subscription_tier == "pro"
    assert updated.rate_limit_rpm == 30

    # Verify that in-memory runtime settings were updated
    assert settings.GEMINI_API_KEY == "new_gemini_key"
    assert settings.GROQ_API_KEY == "new_groq_key"
    assert settings.OLLAMA_API_KEY == "new_ollama_key"


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
        patch("app.services.settings_service.validate_ollama_key", new_callable=AsyncMock) as m_ollama,
        patch("app.services.settings_service.validate_google_cse_keys", new_callable=AsyncMock) as m_cse,
    ):
        from app.schemas.payloads import ProviderValidationStatus

        m_gemini.return_value = ProviderValidationStatus(
            status="valid", message="Connected", model_tested="gemini-2.5-flash"
        )
        m_groq.return_value = ProviderValidationStatus(
            status="valid", message="Connected", model_tested="llama-3.3-70b-versatile"
        )
        m_ollama.return_value = ProviderValidationStatus(
            status="unconfigured", message="No key", model_tested="gpt-oss:120b"
        )
        m_cse.return_value = ProviderValidationStatus(
            status="valid", message="Connected", model_tested="Google CSE"
        )

        resp = await validate_all_settings(None, db_session)
        assert resp.overall_ready is True
        assert resp.gemini.status == "valid"
        assert resp.groq.status == "valid"
        assert resp.ollama.status == "unconfigured"


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
async def test_settings_page_renders_cleanly_without_database_switcher(client):
    """Verifies that the Settings UI does not expose database switcher or raw env config controls."""
    resp = await client.get("/settings")
    assert resp.status_code == 200
    html = resp.text
    # Database switcher must be completely absent from User Settings
    assert "id=\"databaseUrlInput\"" not in html
    assert "id=\"dbChoiceSqlite\"" not in html
    assert "id=\"dbChoicePostgres\"" not in html
    assert "Reset to Default SQLite" not in html
    # Raw Config Editor must be completely removed for security
    assert "Raw Config Editor" not in html
    assert "id=\"rawEnvEditor\"" not in html
    assert "id=\"saveRawEnvBtn\"" not in html
    assert "id=\"env-tab\"" not in html
    assert "id=\"env-pane\"" not in html
    # Ensure primary settings sections remain intact
    assert "Multi-Provider AI Credentials" in html
    assert "Google Custom Search" in html
    assert "Evaluation Strategy" in html


@pytest.mark.asyncio
async def test_database_url_managed_via_server_not_user_settings(db_session):
    """Verifies that user settings cannot arbitrarily switch server database engine and masks credentials."""
    from app.core.database import mask_database_url

    # Updating settings only affects credentials and configuration
    update_req = UserSettingsUpdateRequest(
        gemini_api_key="new_server_test_key",
        subscription_tier="enterprise",
    )
    res = await update_user_settings(update_req, db_session)
    assert res.gemini_api_key_configured is True
    assert res.subscription_tier == "enterprise"

    # Verify password masking
    raw_pg = "postgresql+asyncpg://admin_user:secret_password_123@db.host.com:5432/proddb?ssl=require"
    masked = mask_database_url(raw_pg)
    assert "secret_password_123" not in masked
    assert "••••••••" in masked
    assert "admin_user" in masked

    # Verify API response never leaks raw password or raw .env
    assert "secret_password_123" not in (res.database_url or "")
    assert res.env_content is None


def test_resolve_database_url_hierarchy(tmp_path, monkeypatch):
    """
    Verifies strict DATABASE_URL resolution order:
    1. Read from .env file if it exists and defines DATABASE_URL
    2. If not in .env, read from system environment variables (os.environ)
    3. If neither is set, fall back to default SQLite database file
    """
    from app.core.config import resolve_database_url, DEFAULT_SQLITE_URL

    test_env_file = tmp_path / ".env"

    # Case 1: .env file defines DATABASE_URL -> takes highest priority
    test_env_file.write_text('DATABASE_URL="postgresql://env_user:env_pass@host:5432/env_db"\n')
    monkeypatch.setenv("DATABASE_URL", "postgresql://sys_user:sys_pass@host:5432/sys_db")
    resolved = resolve_database_url(str(test_env_file))
    assert resolved == "postgresql://env_user:env_pass@host:5432/env_db"

    # Case 2: .env does not define DATABASE_URL -> falls back to system environment variable
    test_env_file.write_text('PROJECT_NAME="Test"\n')
    monkeypatch.setenv("DATABASE_URL", "postgresql://sys_user:sys_pass@host:5432/sys_db")
    resolved = resolve_database_url(str(test_env_file))
    assert resolved == "postgresql://sys_user:sys_pass@host:5432/sys_db"

    # Case 3: Neither defines DATABASE_URL -> falls back to default SQLite
    monkeypatch.delenv("DATABASE_URL", raising=False)
    resolved = resolve_database_url(str(test_env_file))
    assert resolved == DEFAULT_SQLITE_URL



@pytest.mark.asyncio
async def test_get_or_create_user_settings_reads_existing_or_creates_defaults(db_session):
    """Verifies that get_or_create_user_settings reads existing DB record if present, or creates defaults if missing."""
    from app.services.settings_service import get_or_create_user_settings
    from app.models.domain import UserSettings
    from sqlalchemy import select, delete

    # Ensure clean state in test DB
    await db_session.execute(delete(UserSettings))
    await db_session.commit()

    # 1. Fresh database -> creates record with defaults
    created = await get_or_create_user_settings(db_session)
    assert created is not None
    assert created.subscription_tier == "standard"
    assert created.evaluation_mode == "llm_cascade"

    # 2. Modify existing record in database
    created.gemini_api_key = "custom_saved_gemini_key"
    created.subscription_tier = "enterprise"
    await db_session.commit()

    # 3. Subsequent call -> reads existing record without wiping it
    fetched = await get_or_create_user_settings(db_session)
    assert fetched.gemini_api_key == "custom_saved_gemini_key"
    assert fetched.subscription_tier == "enterprise"


def test_create_engine_for_url_pooling_and_pre_ping():
    """Verifies that engine pool pre-ping and pooler statement cache settings are applied."""
    from app.core.database import create_engine_for_url

    # 1. SQLite Engine
    sqlite_eng = create_engine_for_url("sqlite+aiosqlite:///./test_pool.db")
    assert sqlite_eng.pool._pre_ping is True
    assert sqlite_eng.pool._recycle == 300

    # 2. Neon / Serverless PgBouncer Engine
    neon_url = "postgresql+asyncpg://user:pass@ep-test-pooler.c-7.us-east-2.aws.neon.tech/kaya_db?ssl=require"
    pg_eng = create_engine_for_url(neon_url)
    assert pg_eng.pool._pre_ping is True
    assert pg_eng.pool._recycle == 300
    assert pg_eng.pool.size() == 10
    assert pg_eng.url.query.get("statement_cache_size") is None  # passed via connect_args


@pytest.mark.asyncio
async def test_validate_ollama_key_unconfigured():
    from app.services.settings_service import validate_ollama_key
    res = await validate_ollama_key("")
    assert res.status == "unconfigured"


@pytest.mark.asyncio
async def test_validate_ollama_key_valid():
    from app.services.settings_service import validate_ollama_key
    with patch("openai.resources.chat.completions.AsyncCompletions.create", new_callable=AsyncMock) as mock_create:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_create.return_value = mock_resp

        res = await validate_ollama_key("valid_ollama_key")
        assert res.status == "valid"
        assert "Ollama Cloud" in res.message


@pytest.mark.asyncio
async def test_validate_ollama_key_invalid():
    from app.services.settings_service import validate_ollama_key
    with patch("openai.resources.chat.completions.AsyncCompletions.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = Exception("401 Unauthorized: Invalid key")

        res = await validate_ollama_key("invalid_key")
        assert res.status == "invalid"
        assert "401" in res.message




