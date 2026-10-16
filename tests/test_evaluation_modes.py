from unittest.mock import AsyncMock, patch
import pytest
from app.core.config import settings
from app.schemas.payloads import CandidateEvaluationResult, UserSettingsUpdateRequest
from app.services.ai_engine import evaluate_candidate
from app.services.settings_service import get_settings_summary, update_user_settings


@pytest.mark.asyncio
async def test_evaluate_candidate_direct_llm_cascade(sample_candidate_evaluation):
    """Verify evaluate_candidate routes 100% directly through the multi-provider LLM cascade."""
    candidate_cv = """
    John Doe
    Email: john@example.com
    Experience:
    Backend Engineer (2020 - 2023)
    Developed FastAPI services and deployed Docker containers, reducing latency by 25%.
    """
    jd = """
    Software Engineer
    Requirements:
    • FastAPI
    • Docker
    • Kubernetes
    """
    valid_json = sample_candidate_evaluation.model_dump_json()

    with patch("app.services.ai_engine._call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = valid_json
        result, provider = await evaluate_candidate(candidate_cv, jd)

        mock_gemini.assert_called_once()
        assert provider == "google/gemini-1.5-flash"
        assert isinstance(result, CandidateEvaluationResult)
        assert result.candidate_name == "Jane Doe"
        assert result.match_percentage == 92
        assert len(result.tailored_interview_questions) >= 1


@pytest.mark.asyncio
async def test_evaluate_candidate_llm_cascade_fallback_to_groq(sample_candidate_evaluation):
    """Verify evaluate_candidate automatically falls back to Groq Llama 3.3 70B when Gemini fails."""
    candidate_cv = """
    David Finance Analyst
    david@finance.com
    Experience:
    Financial Analyst (2019 - 2023)
    Modeled DCF valuations for M&A transactions.
    """
    jd = """
    Senior Analyst
    Requirements:
    • DCF Valuation
    • Bloomberg Terminal
    """
    valid_json = sample_candidate_evaluation.model_dump_json()

    with (
        patch(
            "app.services.ai_engine._call_gemini",
            side_effect=RuntimeError("Google Gemini 429 Too Many Requests / Quota Exceeded"),
        ),
        patch(
            "app.services.ai_engine._call_openai_compatible_provider",
            new_callable=AsyncMock,
            return_value=valid_json,
        ) as mock_groq,
    ):
        result, provider = await evaluate_candidate(candidate_cv, jd)

        assert provider == "groq/llama-3.3-70b-versatile"
        assert isinstance(result, CandidateEvaluationResult)
        assert result.candidate_name == "Jane Doe"
        assert len(result.tailored_interview_questions) >= 1
        mock_groq.assert_called_once()


@pytest.mark.asyncio
async def test_settings_evaluation_mode_persistence_and_sync(db_session):
    """Verify evaluation_mode is persisted to database and synchronized in runtime settings."""
    update_req = UserSettingsUpdateRequest(
        evaluation_mode="llm_cascade",
        subscription_tier="enterprise"
    )
    summary = await update_user_settings(update_req, db_session)

    assert summary.evaluation_mode == "llm_cascade"
    assert settings.EVALUATION_MODE == "llm_cascade"
    assert 'EVALUATION_MODE="llm_cascade"' in summary.env_content

    # Retrieve settings summary to verify persistence
    persisted_summary = await get_settings_summary(db_session)
    assert persisted_summary.evaluation_mode == "llm_cascade"
