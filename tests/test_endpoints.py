from unittest.mock import AsyncMock, patch
import pytest
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
async def test_evaluate_pdf_resume_success(client, sample_candidate_evaluation):
    """Successful PDF upload parses and evaluates candidate."""
    files = {"resume_file": ("resume.pdf", b"%PDF-1.4 test resume pdf bytes", "application/pdf")}
    data = {"job_description": "We need a Senior Python Engineer with FastAPI"}

    clean_cv_text = (
        "John Doe Senior Software Engineer\n"
        "Over 8 years experience building FastAPI backends, Docker containers, and PostgreSQL databases."
    )

    with (
        patch("app.api.v1.endpoints_evaluation.extract_clean_pdf_text", return_value=clean_cv_text),
        patch(
            "app.api.v1.endpoints_evaluation.evaluate_candidate_with_fallback",
            new_callable=AsyncMock,
        ) as mock_eval,
    ):
        mock_eval.return_value = (sample_candidate_evaluation, "google/gemini-2.5-flash")

        response = await client.post("/api/v1/evaluation/resume-pdf", data=data, files=files)
        assert response.status_code == 200
        payload = response.json()

        assert payload["cached"] is False
        assert payload["provider_used"] == "google/gemini-2.5-flash"
        assert payload["analysis"]["candidate_name"] == "Jane Doe"
        assert payload["analysis"]["match_percentage"] == 92
        assert len(payload["analysis"]["tailored_interview_questions"]) == 2


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
    """Invalid URL format must be rejected by Pydantic validation with HTTP 422."""
    data = {
        "job_description": "We need a Senior Python Engineer",
        "portfolio_url": "not-a-valid-http-url",
    }
    response = await client.post("/api/v1/evaluation/portfolio-website", data=data)
    assert response.status_code == 422


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
