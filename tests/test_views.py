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
    assert "rawEnvEditor" in response.text


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

