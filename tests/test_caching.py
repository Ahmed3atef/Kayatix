from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import select
from app.api.v1.endpoints_evaluation import _process_and_cache_evaluation
from app.models.domain import EvaluationCache
from app.services.ai_engine import compute_request_hash


@pytest.mark.asyncio
async def test_sha256_caching_prevents_duplicate_llm_calls(db_session, sample_candidate_evaluation):
    """
    CRITICAL TEST REQUIREMENT:
    Verify that SHA-256 caching prevents duplicate LLM calls,
    preventing unnecessary model invocations.
    """
    candidate_text = "Experienced Senior Python Engineer with 7 years of FastAPI and Kubernetes."
    job_description = "We are seeking a Senior FastAPI engineer with strong backend skills."

    # First execution: Cache Miss -> Must invoke LLM engine
    with patch(
        "app.api.v1.endpoints_evaluation.evaluate_candidate_with_fallback",
        new_callable=AsyncMock,
    ) as mock_eval:
        mock_eval.return_value = (sample_candidate_evaluation, "google/gemini-2.5-flash")

        first_response = await _process_and_cache_evaluation(
            candidate_text=candidate_text,
            job_description=job_description,
            source_type="pdf_resume",
            db=db_session,
        )

        assert first_response.cached is False
        assert first_response.provider_used == "google/gemini-2.5-flash"
        assert first_response.analysis.candidate_name == sample_candidate_evaluation.candidate_name
        mock_eval.assert_called_once()

    # Verify that record was persisted to database with correct hash
    expected_hash = compute_request_hash(candidate_text, job_description)
    stmt = select(EvaluationCache).where(EvaluationCache.request_hash == expected_hash)
    result = await db_session.execute(stmt)
    saved_record = result.scalar_one_or_none()
    assert saved_record is not None
    assert saved_record.request_hash == expected_hash
    assert saved_record.provider_used == "google/gemini-2.5-flash"
    assert saved_record.match_score == sample_candidate_evaluation.match_percentage

    # Second execution: Cache Hit -> Must NOT call LLM engine at all!
    with patch(
        "app.api.v1.endpoints_evaluation.evaluate_candidate_with_fallback",
        new_callable=AsyncMock,
    ) as mock_eval:
        second_response = await _process_and_cache_evaluation(
            candidate_text=candidate_text,
            job_description=job_description,
            source_type="pdf_resume",
            db=db_session,
        )

        assert second_response.cached is True
        assert second_response.provider_used == "google/gemini-2.5-flash"
        assert second_response.analysis.candidate_name == sample_candidate_evaluation.candidate_name
        assert second_response.analysis.match_percentage == sample_candidate_evaluation.match_percentage

        # Zero LLM calls were made! Cache hit served.
        mock_eval.assert_not_called()


@pytest.mark.asyncio
async def test_different_inputs_produce_cache_miss(db_session, sample_candidate_evaluation):
    """Different candidate CV text produces a different hash and causes a cache miss."""
    candidate_1 = "Candidate A with Python skill set."
    candidate_2 = "Candidate B with Rust and Go skill set."
    jd = "Seeking polyglot engineer."

    with patch(
        "app.api.v1.endpoints_evaluation.evaluate_candidate_with_fallback",
        new_callable=AsyncMock,
    ) as mock_eval:
        mock_eval.return_value = (sample_candidate_evaluation, "google/gemini-2.5-flash")

        res1 = await _process_and_cache_evaluation(candidate_1, jd, "pdf_resume", db_session)
        assert res1.cached is False
        assert mock_eval.call_count == 1

        res2 = await _process_and_cache_evaluation(candidate_2, jd, "pdf_resume", db_session)
        assert res2.cached is False
        assert mock_eval.call_count == 2
