import pytest
from app.models.domain import EvaluationCache


@pytest.mark.asyncio
async def test_dashboard_view(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Total Screened Candidates" in response.text
    assert "Average Match Fit" in response.text
    assert "Qualified Shortlist" in response.text
    assert "Average Seniority" in response.text


@pytest.mark.asyncio
async def test_screener_view(client):
    response = await client.get("/screener")
    assert response.status_code == 200
    assert "Resume Screener" in response.text
    assert "dropZone" in response.text


@pytest.mark.asyncio
async def test_portfolio_view(client):
    response = await client.get("/portfolio")
    assert response.status_code == 200
    assert "Portfolio Analyzer" in response.text
    assert "portfolioUrl" in response.text


@pytest.mark.asyncio
async def test_sourcing_view(client):
    response = await client.get("/sourcing")
    assert response.status_code == 200
    assert "LinkedIn X-Ray" in response.text
    assert "xrayJobTitle" in response.text


@pytest.mark.asyncio
async def test_history_view_empty_and_populated(client, db_session, sample_candidate_evaluation):
    # Empty history
    response = await client.get("/history")
    assert response.status_code == 200
    assert "Evaluation History" in response.text

    # Seed one evaluation into DB
    record = EvaluationCache(
        request_hash="a" * 64,
        candidate_name="Test Candidate",
        source_type="pdf_resume",
        match_score=85,
        provider_used="google/gemini-2.5-flash",
        evaluation_json=sample_candidate_evaluation.model_dump(),
    )
    db_session.add(record)
    await db_session.commit()

    # Filtered view
    response = await client.get("/history?q=Test")
    assert response.status_code == 200
    assert "Test Candidate" in response.text


@pytest.mark.asyncio
async def test_settings_view(client):
    response = await client.get("/settings")
    assert response.status_code == 200
    assert "Settings" in response.text
    assert "geminiKey" in response.text
    assert "rawEnvEditor" not in response.text


@pytest.mark.asyncio
async def test_evaluation_detail_view(client, db_session, sample_candidate_evaluation):
    # Insert record
    record = EvaluationCache(
        request_hash="b" * 64,
        candidate_name="Jane Detail",
        source_type="pdf_resume",
        match_score=92,
        provider_used="groq/llama-3.3-70b-versatile",
        evaluation_json=sample_candidate_evaluation.model_dump(),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    response = await client.get(f"/evaluations/{record.id}")
    assert response.status_code == 200
    assert "Jane Doe" in response.text or "Jane Detail" in response.text
    assert "92% Match" in response.text

    # 404 for invalid ID
    not_found = await client.get("/evaluations/99999")
    assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_documentation_view(client):
    """Verifies that /documentation renders the documentation layout with sidebar and sections."""
    response = await client.get("/documentation")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Kayatix Documentation" in response.text
    assert "Documentation" in response.text
    assert "Local Readme Editing" in response.text


@pytest.mark.asyncio
async def test_documentation_page_by_slug(client):
    """Verifies that individual documentation sections can be browsed by slug."""
    # Test specific page: 05-linkedin-xray-sourcing
    response = await client.get("/documentation/05-linkedin-xray-sourcing")
    assert "Zero API Keys" in response.text or "Search Engine ID" in response.text
    assert "05-linkedin-xray-sourcing.md" in response.text


@pytest.mark.asyncio
async def test_footer_ai_provider_indicators(client):
    """Verifies that footer priority pills render green when keys are active and found."""
    from app.core.config import settings
    from app.services.settings_service import provider_health_cache

    # 1. With keys active and valid
    settings.GEMINI_API_KEY = "test_gemini_key"
    settings.GROQ_API_KEY = "test_groq_key"
    settings.OPENROUTER_API_KEY = ""
    provider_health_cache["gemini"] = "valid"
    provider_health_cache["groq"] = "valid"
    provider_health_cache["openrouter"] = "unconfigured"

    resp = await client.get("/")
    assert resp.status_code == 200
    html = resp.text

    assert 'id="footerBadgeGemini"' in html
    assert 'id="footerBadgeGroq"' in html
    assert 'id="footerBadgeOpenRouter"' in html

    # Gemini and Groq should have green badge classes
    assert 'id="footerBadgeGemini" class="badge bg-success-subtle text-success' in html
    assert 'id="footerBadgeGroq" class="badge bg-success-subtle text-success' in html
    # OpenRouter without key should be secondary
    assert 'id="footerBadgeOpenRouter" class="badge bg-secondary-subtle text-secondary' in html


