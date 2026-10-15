from unittest.mock import AsyncMock, patch
import pytest
from app.core.config import settings
from app.schemas.payloads import CandidateEvaluationResult, UserSettingsUpdateRequest
from app.services.ai_engine import HybridSynthesisResult, evaluate_candidate
from app.services.settings_service import get_settings_summary, update_user_settings


@pytest.mark.asyncio
async def test_evaluate_candidate_local_offline_mode():
    """Verify local_offline mode executes without invoking external AI APIs."""
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
    result, provider = await evaluate_candidate(candidate_cv, jd, mode="local_offline")

    assert provider == "local_engine"
    assert isinstance(result, CandidateEvaluationResult)
    assert result.candidate_name == "John Doe"
    assert "FastAPI" in result.matched_skills
    assert "Docker" in result.matched_skills
    assert "Kubernetes" in result.missing_critical_skills
    assert len(result.tailored_interview_questions) >= 1


@pytest.mark.asyncio
async def test_evaluate_candidate_hybrid_mode_with_llm_success():
    """Verify hybrid mode uses local extraction plus LLM for dynamic questions & executive synthesis."""
    candidate_cv = """
    Sarah Marketing Director
    sarah@marketing.org
    Experience:
    Marketing Director (Jan 2019 - Present)
    Spearheaded enterprise brand strategy delivering $2.5M in revenue.
    """
    jd = """
    Marketing Director
    Requirements:
    • Brand Strategy
    • HubSpot
    """
    mock_synthesis = HybridSynthesisResult(
        executive_summary="Sarah is an accomplished marketing director with proven pipeline generation.",
        tailored_interview_questions=[
            {
                "category": "Technical",
                "question": "How have you structured HubSpot automation sequences for complex enterprise B2B sales cycles?",
                "target_area": "HubSpot Execution",
                "expected_answer_criteria": "Discusses lead scoring, CRM integration, and lifecycle stage triggers."
            }
        ]
    )

    with patch(
        "app.services.ai_engine._generate_dynamic_questions_and_synthesis_from_llm",
        new_callable=AsyncMock,
        return_value=(mock_synthesis, "google/gemini-2.5-flash")
    ) as mock_llm:
        result, provider = await evaluate_candidate(candidate_cv, jd, mode="hybrid")

        mock_llm.assert_called_once()
        assert "hybrid (local + google/gemini-2.5-flash)" in provider
        assert result.executive_summary == mock_synthesis.executive_summary
        assert result.tailored_interview_questions[0].target_area == "HubSpot Execution"
        assert "Brand Strategy" in result.matched_skills


@pytest.mark.asyncio
async def test_evaluate_candidate_hybrid_mode_fallback_when_llm_fails():
    """Verify hybrid mode safely falls back to local baseline questions when LLM is rate-limited or fails."""
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

    with patch(
        "app.services.ai_engine._generate_dynamic_questions_and_synthesis_from_llm",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Google Gemini 429 Too Many Requests / Quota Exceeded"),
    ):
        result, provider = await evaluate_candidate(candidate_cv, jd, mode="hybrid")

        assert provider == "hybrid (local_engine)"
        assert isinstance(result, CandidateEvaluationResult)
        assert "DCF Valuation" in result.matched_skills
        assert "Bloomberg Terminal" in result.missing_critical_skills
        assert len(result.tailored_interview_questions) >= 1


@pytest.mark.asyncio
async def test_settings_evaluation_mode_persistence_and_sync(db_session):
    """Verify evaluation_mode is persisted to database and synchronized in runtime settings."""
    # Update evaluation mode to local_offline
    update_req = UserSettingsUpdateRequest(
        evaluation_mode="local_offline",
        subscription_tier="enterprise"
    )
    summary = await update_user_settings(update_req, db_session)

    assert summary.evaluation_mode == "local_offline"
    assert settings.EVALUATION_MODE == "local_offline"
    assert 'EVALUATION_MODE="local_offline"' in summary.env_content

    # Retrieve settings summary to verify persistence
    persisted_summary = await get_settings_summary(db_session)
    assert persisted_summary.evaluation_mode == "local_offline"

