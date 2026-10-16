import io
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from app.core.config import settings
from app.schemas.payloads import XRaySearchRequest
from app.services.pdf_service import extract_clean_pdf_text
from app.services.scraper_service import scrape_candidate_portfolio
from app.services.sourcing_service import execute_linkedin_xray_search


# --- PDF Service Tests ---

def test_extract_clean_pdf_text_corrupted_bytes():
    with pytest.raises(ValueError, match="Corrupted or unreadable PDF file"):
        extract_clean_pdf_text(b"not a valid pdf content")


def test_extract_clean_pdf_text_scanned_image_too_short():
    # Mock pypdf reader returning very short text
    with patch("pypdf.PdfReader") as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Short"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        with pytest.raises(ValueError, match="scanned image without selectable text"):
            extract_clean_pdf_text(b"%PDF-1.4 dummy")


def test_extract_clean_pdf_text_success():
    sample_text = (
        "Jane Doe\n"
        "Senior Backend Engineer with extensive experience in building scalable Python microservices.\n"
        "Proficient in FastAPI, Docker, and PostgreSQL with a proven track record of delivering resilient APIs."
    )
    with patch("pypdf.PdfReader") as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sample_text
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        result = extract_clean_pdf_text(b"%PDF-1.4 dummy", max_chars=18000)
        assert "Jane Doe" in result
        assert "Senior Backend Engineer" in result
        assert len(result) > 50


# --- Portfolio Scraper Service Tests ---

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
        patch("httpx.AsyncClient.get") as mock_get,
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = '{"error": {"code": 403, "message": "This project does not have the access to Custom Search JSON API.", "status": "PERMISSION_DENIED"}}'
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Google has restricted the legacy Custom Search JSON API"):
            await execute_linkedin_xray_search(req)
