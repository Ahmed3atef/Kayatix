from unittest.mock import AsyncMock, patch
import pytest
from app.core.config import settings
from app.schemas.payloads import XRayProfileItem


@pytest.mark.asyncio
async def test_health_check_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "version" in data


@pytest.mark.asyncio
async def test_evaluate_pdf_resume_non_pdf_rejection(client):
    """Endpoints must reject non-PDF files with HTTP 400."""
    files = {"resume_file": ("resume.docx", b"dummy word content", "application/msword")}
    data = {"job_description": "We need a Senior Python Engineer"}

    response = await client.post("/api/v1/evaluation/resume-pdf", data=data, files=files)
    assert response.status_code == 400
    assert "Only PDF files are accepted" in response.json()["detail"]


@pytest.mark.asyncio
async def test_evaluate_pdf_resume_success(client):
    """Successful PDF upload parses and evaluates candidate via single-shot evaluation."""
    files = {"resume_file": ("resume.pdf", b"%PDF-1.4 test resume pdf bytes", "application/pdf")}
    data = {"job_description": "We need a Senior Python Engineer with FastAPI"}

    from app.services.ai_evaluator import HRAnalysisResult, InterviewQuestion
    hr_result = HRAnalysisResult(
        candidate_name="Jane Doe",
        match_percentage=92,
        matched_skills=["Python", "FastAPI"],
        missing_critical_skills=[],
        years_of_experience=6.5,
        executive_summary="Strong match for FastAPI role.",
        red_flags=[],
        tailored_interview_questions=[
            InterviewQuestion(
                category="Technical",
                question="Explain FastAPI dependency injection.",
                target_skill_or_gap="FastAPI Depends",
                expected_answer_criteria="Yield and sub-dependencies.",
            ),
            InterviewQuestion(
                category="System Design",
                question="How do you handle async background tasks?",
                target_skill_or_gap="Async architecture",
                expected_answer_criteria="Celery, Redis, or asyncio tasks.",
            ),
        ],
    )

    with patch(
        "app.api.v1.endpoints_evaluation.evaluate_candidate_pipeline",
        new_callable=AsyncMock,
        return_value=(hr_result, "gemini-2.5-flash-single-shot"),
    ) as mock_eval:
        response = await client.post("/api/v1/evaluation/resume-pdf", data=data, files=files)
        assert response.status_code == 200
        payload = response.json()

        assert payload["cached"] is False
        assert payload["provider_used"] == "gemini-2.5-flash-single-shot"
        assert payload["analysis"]["candidate_name"] == "Jane Doe"
        assert payload["analysis"]["match_percentage"] == 92
        assert payload["extraction_method"] == "gemini-2.5-flash-single-shot"
        assert len(payload["analysis"]["tailored_interview_questions"]) == 2
        mock_eval.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_pdf_resume_with_pypdf_fallback(client):
    """Verifies that PDF resume evaluation uses pypdf fallback when single-shot falls back."""
    files = {"resume_file": ("resume_scanned.pdf", b"%PDF-1.4 scanned bytes", "application/pdf")}
    data = {"job_description": "We need a Senior Python Engineer with FastAPI"}

    from app.services.ai_evaluator import HRAnalysisResult
    hr_result = HRAnalysisResult(
        candidate_name="Jane Doe",
        match_percentage=92,
        matched_skills=["Python", "FastAPI"],
        missing_critical_skills=[],
        years_of_experience=6.5,
        executive_summary="Evaluated via pypdf fallback.",
        red_flags=[],
        tailored_interview_questions=[],
    )

    with patch(
        "app.api.v1.endpoints_evaluation.evaluate_candidate_pipeline",
        new_callable=AsyncMock,
        return_value=(hr_result, "pypdf_local_parser+groq-llama-3.3-70b"),
    ) as mock_eval:
        response = await client.post("/api/v1/evaluation/resume-pdf", data=data, files=files)
        assert response.status_code == 200
        payload = response.json()

        assert payload["extraction_method"] == "pypdf_local_parser+groq-llama-3.3-70b"
        assert payload["provider_used"] == "pypdf_local_parser+groq-llama-3.3-70b"
        assert payload["analysis"]["candidate_name"] == "Jane Doe"
        assert payload["analysis"]["match_percentage"] == 92
        mock_eval.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_portfolio_website_success(client, sample_candidate_evaluation):
    """Successful candidate portfolio evaluation."""
    data = {
        "job_description": "We need a Senior Python Engineer with FastAPI",
        "portfolio_url": "https://janedoe.dev",
    }
    scraped_text = (
        "Jane Doe - Portfolio and Technical Blog\n"
        "Staff Engineer with 10 years experience in distributed systems, async architectures, and cloud native tools."
    )

    with (
        patch(
            "app.api.v1.endpoints_evaluation.scrape_candidate_portfolio",
            new_callable=AsyncMock,
            return_value=scraped_text,
        ),
        patch(
            "app.api.v1.endpoints_evaluation.evaluate_candidate_with_fallback",
            new_callable=AsyncMock,
        ) as mock_eval,
    ):
        mock_eval.return_value = (sample_candidate_evaluation, "groq/llama-3.3-70b-versatile")

        response = await client.post("/api/v1/evaluation/portfolio-website", data=data)
        assert response.status_code == 200
        payload = response.json()

        assert payload["cached"] is False
        assert payload["provider_used"] == "groq/llama-3.3-70b-versatile"
        assert payload["analysis"]["match_percentage"] == 92


@pytest.mark.asyncio
async def test_evaluate_portfolio_website_invalid_url(client):
    """Invalid URL format must be rejected with HTTP 422."""
    data = {
        "job_description": "We need a Senior Python Engineer",
        "portfolio_url": "not-a-valid-http-url",
    }
    response = await client.post("/api/v1/evaluation/portfolio-website", data=data)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_evaluate_portfolio_website_direct_text_fallback(client, sample_candidate_evaluation):
    """Direct portfolio text fallback evaluates successfully without network scraping."""
    data = {
        "job_description": "We need a Senior Python Engineer with Docker and FastAPI experience",
        "portfolio_text": "Jane Doe - Senior Full Stack Engineer. Specializing in Python, FastAPI, Docker, and AWS.",
    }
    with patch(
        "app.api.v1.endpoints_evaluation.evaluate_candidate_with_fallback",
        new_callable=AsyncMock,
    ) as mock_eval:
        mock_eval.return_value = (sample_candidate_evaluation, "local_offline")
        response = await client.post("/api/v1/evaluation/portfolio-website", data=data)
        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis"]["candidate_name"] == "Jane Doe"


@pytest.mark.asyncio
async def test_evaluate_portfolio_website_spa_fallback_success(client, sample_candidate_evaluation):
    """SPA website with zero static text gracefully evaluates via dynamic fallback without 422."""
    data = {
        "job_description": "We need a Senior Engineer",
        "portfolio_url": "https://ahmed-atef.vercel.app",
    }
    with (
        patch(
            "app.api.v1.endpoints_evaluation.scrape_candidate_portfolio",
            side_effect=ValueError("Could not extract sufficient readable text (< 30 characters)"),
        ),
        patch(
            "app.api.v1.endpoints_evaluation.evaluate_candidate_with_fallback",
            new_callable=AsyncMock,
        ) as mock_eval,
    ):
        mock_eval.return_value = (sample_candidate_evaluation, "hybrid")
        response = await client.post("/api/v1/evaluation/portfolio-website", data=data)
        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis"]["candidate_name"] == "Jane Doe"




@pytest.mark.asyncio
async def test_discover_candidates_via_xray_success(client):
    """X-Ray sourcing endpoint returns discovered profiles."""
    payload = {
        "job_title": "Senior Backend Engineer",
        "required_skills": ["Python", "FastAPI", "PostgreSQL"],
        "location": "Cairo, Egypt",
        "max_results": 2,
    }

    mock_profiles = [
        XRayProfileItem(
            full_title="Tarek Ali - Lead Backend Engineer - Tech Hub | LinkedIn",
            linkedin_url="https://www.linkedin.com/in/tarek-ali-1234",
            snippet="Lead Backend Engineer in Cairo specializing in Python, FastAPI, and PostgreSQL microservices.",
        )
    ]

    with patch(
        "app.api.v1.endpoints_sourcing.execute_linkedin_xray_search",
        new_callable=AsyncMock,
        return_value=mock_profiles,
    ):
        response = await client.post("/api/v1/sourcing/linkedin-xray", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["full_title"] == "Tarek Ali - Lead Backend Engineer - Tech Hub | LinkedIn"
        assert "tarek-ali-1234" in data[0]["linkedin_url"]
