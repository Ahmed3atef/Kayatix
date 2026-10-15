import json
from unittest.mock import AsyncMock, patch
import pytest
from app.schemas.payloads import CandidateEvaluationResult
from app.services.ai_engine import (
    _clean_json_string,
    compute_request_hash,
    evaluate_candidate_with_fallback,
)


def test_compute_request_hash_deterministic():
    cv = "Senior Software Engineer with 8 years experience in Python and Cloud."
    jd = "Seeking Senior Backend Engineer proficient in Python, Docker, and SQL."

    hash1 = compute_request_hash(cv, jd)
    hash2 = compute_request_hash(cv, jd)
    hash3 = compute_request_hash(cv + " additional info", jd)

    assert hash1 == hash2
    assert len(hash1) == 64
    assert hash1 != hash3


def test_clean_json_string_with_markdown_blocks():
    raw_markdown = """```json
    {
      "candidate_name": "Alice Smith",
      "match_percentage": 88
    }
    ```"""
    cleaned = _clean_json_string(raw_markdown)
    parsed = json.loads(cleaned)
    assert parsed["candidate_name"] == "Alice Smith"
    assert parsed["match_percentage"] == 88


@pytest.mark.asyncio
async def test_evaluate_candidate_primary_gemini_success(sample_candidate_evaluation):
    valid_json = sample_candidate_evaluation.model_dump_json()

    with patch("app.services.ai_engine._call_gemini", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = valid_json

        result, provider = await evaluate_candidate_with_fallback(
            candidate_text="Jane Doe CV Text",
            job_description="Python Backend Engineer JD",
        )

        assert provider == "google/gemini-2.5-flash"
        assert result.candidate_name == "Jane Doe"
        assert result.match_percentage == 92
        mock_gemini.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_candidate_fallback_to_groq_when_gemini_fails(sample_candidate_evaluation):
    """
    CRITICAL TEST REQUIREMENT:
    When Gemini raises a RateLimit/Exception (e.g. 429 Too Many Requests),
    the engine automatically falls back to Groq and returns a valid CandidateEvaluationResult.
    """
    valid_json = sample_candidate_evaluation.model_dump_json()

    with (
        patch(
            "app.services.ai_engine._call_gemini",
            side_effect=Exception("HTTP 429: Resource has been exhausted (e.g. check quota)"),
        ) as mock_gemini,
        patch(
            "app.services.ai_engine._call_openai_compatible_provider",
            new_callable=AsyncMock,
        ) as mock_openai_provider,
    ):
        mock_openai_provider.return_value = valid_json

        result, provider = await evaluate_candidate_with_fallback(
            candidate_text="Jane Doe CV Text",
            job_description="Python Backend Engineer JD",
        )

        # Gemini was attempted
        mock_gemini.assert_called_once()

        # Engine fell over to Groq
        assert provider == "groq/llama-3.3-70b-versatile"
        assert result.candidate_name == "Jane Doe"
        assert result.match_percentage == 92
        assert len(result.tailored_interview_questions) == 2

        # Verify Groq was called with the correct parameters
        mock_openai_provider.assert_called_once()
        args, kwargs = mock_openai_provider.call_args
        assert kwargs["model_name"] == "llama-3.3-70b-versatile"
        assert "api.groq.com" in kwargs["base_url"]


@pytest.mark.asyncio
async def test_evaluate_candidate_fallback_to_openrouter_when_gemini_and_groq_fail(sample_candidate_evaluation):
    """
    When both Gemini (429) and Groq (429) fail,
    the engine cascades down to OpenRouter :free pool.
    """
    valid_json = sample_candidate_evaluation.model_dump_json()

    with (
        patch(
            "app.services.ai_engine._call_gemini",
            side_effect=Exception("Gemini Quota Exceeded 429"),
        ),
        patch(
            "app.services.ai_engine._call_openai_compatible_provider",
            side_effect=[
                Exception("Groq Rate Limit Exceeded 429"),
                valid_json,  # OpenRouter succeeds
            ],
        ) as mock_openai_provider,
    ):
        result, provider = await evaluate_candidate_with_fallback(
            candidate_text="Jane Doe CV Text",
            job_description="Python Backend Engineer JD",
        )

        assert provider == "openrouter/llama-3.1-8b-instruct:free"
        assert result.candidate_name == "Jane Doe"
        assert mock_openai_provider.call_count == 2


@pytest.mark.asyncio
async def test_evaluate_candidate_all_providers_exhausted():
    """
    When Gemini, Groq, and OpenRouter all fail,
    a descriptive RuntimeError is raised.
    """
    with (
        patch("app.services.ai_engine._call_gemini", side_effect=Exception("Gemini Down")),
        patch(
            "app.services.ai_engine._call_openai_compatible_provider",
            side_effect=Exception("Provider 429 Throttled"),
        ),
    ):
        with pytest.raises(RuntimeError, match="All configured AI providers are currently rate-limited"):
            await evaluate_candidate_with_fallback(
                candidate_text="Jane Doe CV Text",
                job_description="Python Backend Engineer JD",
            )
