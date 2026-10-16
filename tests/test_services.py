from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.core.config import settings
from app.schemas.payloads import XRaySearchRequest
from app.services.pdf_service import (
    encode_pdf_to_base64,
    extract_pdf_content,
    extract_text_with_gemini_vision,
    extract_text_with_mistral_ocr,
    extract_text_with_llamaparse,
)
from app.services.ai_evaluator import (
    evaluate_candidate_pipeline,
    HRAnalysisResult,
    InterviewQuestion,
)
from app.services.scraper_service import scrape_candidate_portfolio
from app.services.sourcing_service import execute_linkedin_xray_search


# --- Cloud PDF OCR Tests ---

def test_encode_pdf_to_base64():
    raw = b"%PDF-1.4 test dummy content"
    b64 = encode_pdf_to_base64(raw)
    assert isinstance(b64, str)
    assert len(b64) > 0


@pytest.mark.asyncio
async def test_extract_text_with_gemini_vision_missing_key():
    with patch.object(settings, "GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
            await extract_text_with_gemini_vision(b"%PDF dummy", api_key=None)


@pytest.mark.asyncio
async def test_extract_text_with_gemini_vision_insufficient_text():
    mock_resp = MagicMock()
    mock_resp.text = "Too short"
    with (
        patch("google.genai.Client") as mock_client_cls,
        patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp),
    ):
        with pytest.raises(RuntimeError, match="insufficient text"):
            await extract_text_with_gemini_vision(b"%PDF dummy", api_key="dummy_gemini_key")


@pytest.mark.asyncio
async def test_extract_text_with_gemini_vision_success():
    expected_md = (
        "# John Doe\n\n"
        "Senior Cloud Architect with extensive experience in GCP, Terraform, and Python.\n"
        "Led multiple large-scale infrastructure transformations with high availability."
    )
    mock_resp = MagicMock()
    mock_resp.text = expected_md

    with (
        patch("google.genai.Client") as mock_client_cls,
        patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp),
    ):
        result = await extract_text_with_gemini_vision(
            b"%PDF dummy bytes", api_key="dummy_gemini_key"
        )
        assert "John Doe" in result
        assert "Senior Cloud Architect" in result


# --- Mistral AI OCR Tests ---

@pytest.mark.asyncio
async def test_extract_text_with_mistral_ocr_missing_key():
    with patch.object(settings, "MISTRAL_API_KEY", None):
        with pytest.raises(ValueError, match="MISTRAL_API_KEY is not configured"):
            await extract_text_with_mistral_ocr(b"%PDF dummy bytes", api_key=None)


@pytest.mark.asyncio
async def test_extract_text_with_mistral_ocr_httpx_success():
    mock_ocr_response = {
        "pages": [
            {
                "index": 0,
                "markdown": "# Sarah Connor\nStaff Site Reliability Engineer with Kubernetes expertise.",
            },
            {
                "index": 1,
                "markdown": "## Experience\n- Lead Infrastructure Architect at TechCorp\n- Implemented zero-downtime CI/CD",
            },
        ],
        "model": "mistral-ocr-latest",
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_ocr_response
        mock_post.return_value = mock_resp

        markdown_text = await extract_text_with_mistral_ocr(
            b"%PDF-1.4 dummy resume", api_key="test_mistral_key"
        )

        assert "Sarah Connor" in markdown_text
        assert "Staff Site Reliability Engineer" in markdown_text
        assert "Page 1" in markdown_text
        assert "Page 2" in markdown_text


@pytest.mark.asyncio
async def test_extract_text_with_mistral_ocr_rate_limit_retry():
    """Verifies that 429 triggers exponential backoff retry on free tier."""
    mock_ocr_response = {
        "pages": [{"index": 0, "markdown": "Extracted text after rate limit retry with sufficient length for test."}],
    }

    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.text = "Rate limit exceeded"

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = mock_ocr_response

    with (
        patch("httpx.AsyncClient.post", side_effect=[mock_resp_429, mock_resp_200]) as mock_post,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await extract_text_with_mistral_ocr(
            b"%PDF dummy", api_key="valid_key", max_retries=2, initial_backoff=0.01
        )
        assert "Extracted text after rate limit retry" in result
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once()


# --- LlamaParse Cloud Tests ---

@pytest.mark.asyncio
async def test_extract_text_with_llamaparse_missing_key():
    with patch.object(settings, "LLAMA_CLOUD_API_KEY", None):
        with pytest.raises(ValueError, match="LLAMA_CLOUD_API_KEY is not configured"):
            await extract_text_with_llamaparse(b"%PDF dummy bytes", api_key=None)


@pytest.mark.asyncio
async def test_extract_text_with_llamaparse_success():
    with (
        patch("httpx.AsyncClient.post") as mock_post,
        patch("httpx.AsyncClient.get") as mock_get,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        upload_resp = MagicMock(status_code=200)
        upload_resp.json.return_value = {"id": "llama_job_123"}
        mock_post.return_value = upload_resp

        status_resp = MagicMock(status_code=200)
        status_resp.json.return_value = {"status": "SUCCESS"}

        result_resp = MagicMock(status_code=200)
        result_resp.json.return_value = {
            "markdown": "# Leila Ahmed\nLead AI Engineer with NLP and LLM fine-tuning experience."
        }
        mock_get.side_effect = [status_resp, result_resp]

        extracted = await extract_text_with_llamaparse(b"%PDF dummy", api_key="test_llama_key")
        assert "Leila Ahmed" in extracted
        assert "Lead AI Engineer" in extracted


# --- Cloud OCR Pipeline Fallbacks ---

@pytest.mark.asyncio
async def test_extract_pdf_content_tier1_gemini():
    with patch(
        "app.services.pdf_service.extract_text_with_gemini_vision",
        new_callable=AsyncMock,
        return_value="Alex Developer - Senior Backend Engineer with FastAPI & Docker experience",
    ):
        text, method = await extract_pdf_content(b"%PDF dummy", gemini_api_key="valid_key")
        assert method == "gemini_vision_ocr"
        assert "Alex Developer" in text


@pytest.mark.asyncio
async def test_extract_pdf_content_tier2_mistral_fallback():
    with (
        patch(
            "app.services.pdf_service.extract_text_with_gemini_vision",
            side_effect=RuntimeError("Gemini rate limit 429"),
        ),
        patch(
            "app.services.pdf_service.extract_text_with_mistral_ocr",
            new_callable=AsyncMock,
            return_value="Maria Lead - DevOps Architect with Kubernetes and Terraform experience",
        ),
    ):
        text, method = await extract_pdf_content(
            b"%PDF dummy", gemini_api_key="failing_key", mistral_api_key="valid_key"
        )
        assert method == "mistral_ocr"
        assert "Maria Lead" in text


@pytest.mark.asyncio
async def test_extract_pdf_content_tier3_llamaparse_fallback():
    with (
        patch(
            "app.services.pdf_service.extract_text_with_gemini_vision",
            side_effect=RuntimeError("Gemini failed"),
        ),
        patch(
            "app.services.pdf_service.extract_text_with_mistral_ocr",
            side_effect=RuntimeError("Mistral failed"),
        ),
        patch(
            "app.services.pdf_service.extract_text_with_llamaparse",
            new_callable=AsyncMock,
            return_value="Tariq Cloud - Cloud Solutions Architect with AWS, Azure, and GCP",
        ),
    ):
        text, method = await extract_pdf_content(
            b"%PDF dummy", llama_api_key="valid_key"
        )
        assert method == "llamaparse_cloud"
        assert "Tariq Cloud" in text


@pytest.mark.asyncio
async def test_extract_pdf_content_all_fail():
    with (
        patch(
            "app.services.pdf_service.extract_text_with_gemini_vision",
            side_effect=RuntimeError("Gemini failed"),
        ),
        patch(
            "app.services.pdf_service.extract_text_with_mistral_ocr",
            side_effect=RuntimeError("Mistral failed"),
        ),
        patch(
            "app.services.pdf_service.extract_text_with_llamaparse",
            side_effect=RuntimeError("LlamaParse failed"),
        ),
    ):
        with pytest.raises(RuntimeError, match="All cloud PDF OCR providers failed"):
            await extract_pdf_content(b"%PDF dummy")


# --- AI Evaluator Pipeline Tests ---

@pytest.mark.asyncio
async def test_ai_evaluator_single_shot_gemini():
    mock_hr_result = HRAnalysisResult(
        candidate_name="Jane Doe",
        match_percentage=94,
        matched_skills=["Python", "FastAPI", "Docker"],
        missing_critical_skills=[],
        years_of_experience=7.5,
        executive_summary="Exceptional fit for senior engineering role.",
        red_flags=[],
        tailored_interview_questions=[
            InterviewQuestion(
                category="Technical",
                question="How do you handle connection pooling in async SQLAlchemy?",
                target_skill_or_gap="SQLAlchemy async pooling",
                expected_answer_criteria="Mentions null pool or pool_size and pre-ping.",
            )
        ],
    )
    mock_resp = MagicMock()
    mock_resp.text = mock_hr_result.model_dump_json()

    with (
        patch.object(settings, "GEMINI_API_KEY", "test_gemini_key"),
        patch("google.genai.Client"),
        patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp),
    ):
        res, pipeline = await evaluate_candidate_pipeline(
            pdf_bytes=b"%PDF dummy",
            job_description="Senior Python Engineer with FastAPI and Docker",
        )
        assert pipeline == "gemini-2.5-flash-single-shot"
        assert res.candidate_name == "Jane Doe"
        assert res.match_percentage == 94


@pytest.mark.asyncio
async def test_ai_evaluator_fallback_to_groq_when_gemini_fails():
    mock_hr_result = HRAnalysisResult(
        candidate_name="Omar Tariq",
        match_percentage=88,
        matched_skills=["Python", "PostgreSQL"],
        missing_critical_skills=["Kubernetes"],
        years_of_experience=5.0,
        executive_summary="Solid backend engineer with strong database skills.",
        red_flags=[],
        tailored_interview_questions=[],
    )

    with (
        patch.object(settings, "GEMINI_API_KEY", "failing_gemini_key"),
        patch.object(settings, "GROQ_API_KEY", "valid_groq_key"),
        patch("google.genai.Client", side_effect=RuntimeError("Gemini quota 429")),
        patch(
            "app.services.ai_evaluator.extract_pdf_content",
            new_callable=AsyncMock,
            return_value=("Extracted Resume Markdown Content", "mistral_ocr"),
        ),
        patch("app.services.ai_evaluator.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_groq_client = MagicMock()
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = mock_hr_result.model_dump_json()
        mock_completion.choices = [mock_choice]
        mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_openai_cls.return_value = mock_groq_client

        res, pipeline = await evaluate_candidate_pipeline(
            pdf_bytes=b"%PDF dummy",
            job_description="Backend Engineer",
        )
        assert "groq-llama-3.3-70b" in pipeline
        assert res.candidate_name == "Omar Tariq"
        assert res.match_percentage == 88


# --- Scraper Service Tests ---

@pytest.mark.asyncio
async def test_scrape_candidate_portfolio_http_error():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Website returned HTTP 404"):
            await scrape_candidate_portfolio("https://example.com/nonexistent")


@pytest.mark.asyncio
async def test_scrape_candidate_portfolio_too_short_text():
    with (
        patch("httpx.AsyncClient.get") as mock_get,
        patch("trafilatura.extract") as mock_extract,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Short</body></html>"
        mock_get.return_value = mock_response

        mock_extract.return_value = "Too short"

        with pytest.raises(ValueError, match="Could not extract sufficient readable text"):
            await scrape_candidate_portfolio("https://example.com/portfolio")


@pytest.mark.asyncio
async def test_scrape_candidate_portfolio_success():
    rich_text = (
        "Alice Smith - Senior Systems Engineer\n"
        "Welcome to my technical portfolio. I have spent the last 8 years specializing in distributed systems, "
        "Kubernetes orchestration, and high-performance backend development in Python and Go."
    )
    with (
        patch("httpx.AsyncClient.get") as mock_get,
        patch("trafilatura.extract") as mock_extract,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Full Page Content</body></html>"
        mock_get.return_value = mock_response

        mock_extract.return_value = rich_text

        extracted = await scrape_candidate_portfolio("https://example.com/portfolio")
        assert "Alice Smith" in extracted
        assert "distributed systems" in extracted


# --- Sourcing Service Tests ---

@pytest.mark.asyncio
async def test_execute_linkedin_xray_search_missing_credentials():
    req = XRaySearchRequest(
        job_title="Backend Engineer",
        required_skills=["Python", "FastAPI"],
        location="Cairo",
    )
    with (
        patch.object(settings, "GOOGLE_CSE_API_KEY", None),
        patch.object(settings, "GOOGLE_CSE_CX_ID", None),
        patch.object(settings, "GEMINI_API_KEY", None),
        patch("app.core.database.AsyncSessionLocal", side_effect=Exception("No DB")),
    ):
        with pytest.raises(ValueError, match="Google Custom Search API credentials are not configured"):
            await execute_linkedin_xray_search(req)


@pytest.mark.asyncio
async def test_execute_linkedin_xray_search_success():
    req = XRaySearchRequest(
        job_title="Senior Python Engineer",
        required_skills=["FastAPI", "Docker"],
        location="Berlin",
        max_results=2,
    )

    mock_google_response = {
        "items": [
            {
                "title": "Alex Developer - Senior Python Engineer - Tech Corp | LinkedIn",
                "link": "https://www.linkedin.com/in/alex-dev-12345",
                "snippet": "Experienced Python Engineer specializing in FastAPI and cloud architectures.",
            },
            {
                "title": "Maria Senior - Tech Lead - Cloud Solutions | LinkedIn",
                "link": "https://www.linkedin.com/in/maria-senior-67890",
                "snippet": "Backend Lead with 7+ years of experience in Docker, Kubernetes, and Python APIs.",
            },
        ]
    }

    with (
        patch.object(settings, "GOOGLE_CSE_API_KEY", "valid_key"),
        patch.object(settings, "GOOGLE_CSE_CX_ID", "valid_cx"),
        patch("httpx.AsyncClient.get") as mock_get,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_google_response
        mock_get.return_value = mock_resp

        results = await execute_linkedin_xray_search(req)
        assert len(results) == 2
        assert results[0].full_title == "Alex Developer - Senior Python Engineer - Tech Corp | LinkedIn"
        assert results[0].linkedin_url == "https://www.linkedin.com/in/alex-dev-12345"
        assert "FastAPI" in results[0].snippet


@pytest.mark.asyncio
async def test_execute_linkedin_xray_search_api_error():
    req = XRaySearchRequest(
        job_title="Backend Engineer",
        required_skills=["Python"],
        location="Remote",
    )
    with (
        patch.object(settings, "GOOGLE_CSE_API_KEY", "valid_key"),
        patch.object(settings, "GOOGLE_CSE_CX_ID", "valid_cx"),
        patch("httpx.AsyncClient.get") as mock_get,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Quota exceeded for Google Custom Search"
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Google Search API error"):
            await execute_linkedin_xray_search(req)


@pytest.mark.asyncio
async def test_execute_linkedin_xray_search_google_new_project_restriction():
    req = XRaySearchRequest(
        job_title="ERPNext Developer",
        required_skills=["Frappe", "Python"],
        location="Cairo",
    )
    with (
        patch.object(settings, "GOOGLE_CSE_API_KEY", "valid_key"),
        patch.object(settings, "GOOGLE_CSE_CX_ID", "valid_cx"),
        patch.object(settings, "GEMINI_API_KEY", None),
        patch("httpx.AsyncClient.get") as mock_get,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = '{"error": {"code": 403, "message": "This project does not have the access to Custom Search JSON API.", "status": "PERMISSION_DENIED"}}'
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Google has restricted the legacy Custom Search JSON API"):
            await execute_linkedin_xray_search(req)
