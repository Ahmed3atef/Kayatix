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
