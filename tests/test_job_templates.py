import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.settings_service import (
    get_all_job_templates,
    get_job_template_by_id,
    create_job_template,
    update_job_template,
    delete_job_template,
    reset_default_job_templates,
)
from app.schemas.payloads import JobTemplateCreateRequest, JobTemplateUpdateRequest


@pytest.mark.asyncio
async def test_job_templates_service_lifecycle(db_session):
    """Verifies service functions for job description templates."""
    # 1. Initial get seeds defaults
    templates = await get_all_job_templates(db_session)
    assert len(templates) >= 6
    titles = [t.title for t in templates]
    assert "FastAPI Backend Engineer" in titles
    assert "Talent Acquisition & HR Lead" in titles

    # 2. Create custom template
    create_req = JobTemplateCreateRequest(
        title="Senior Security Architect",
        category="Security",
        description="Job Title: Senior Security Architect\nRequirements:\n- 7+ years cyber defense\n- SOC2 / ISO 27001",
    )
    created = await create_job_template(db_session, create_req)
    assert created.id is not None
    assert created.title == "Senior Security Architect"
    assert created.category == "Security"

    # 3. Get by ID
    fetched = await get_job_template_by_id(db_session, created.id)
    assert fetched is not None
    assert fetched.title == "Senior Security Architect"

    # 4. Update template
    update_req = JobTemplateUpdateRequest(
        title="Principal Security Architect",
        description="Updated security requirements",
    )
    updated = await update_job_template(db_session, created.id, update_req)
    assert updated.title == "Principal Security Architect"
    assert updated.description == "Updated security requirements"

    # 5. Delete template
    deleted = await delete_job_template(db_session, created.id)
    assert deleted is True

    # 6. Verify deleted
    not_found = await get_job_template_by_id(db_session, created.id)
    assert not_found is None


@pytest.mark.asyncio
async def test_job_templates_api_endpoints(db_session):
    """Verifies REST API endpoints for job description templates."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # GET /api/v1/settings/templates
        resp = await ac.get("/api/v1/settings/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert len(templates) >= 6

        # POST /api/v1/settings/templates
        new_payload = {
            "title": "Staff AI Research Engineer",
            "category": "Artificial Intelligence",
            "description": "Job Title: Staff AI Research Engineer\nRequirements:\n- LLM fine-tuning, RLHF, PyTorch",
        }
        create_resp = await ac.post("/api/v1/settings/templates", json=new_payload)
        assert create_resp.status_code == 201
        created_data = create_resp.json()
        template_id = created_data["id"]
        assert created_data["title"] == "Staff AI Research Engineer"

        # GET /api/v1/settings/templates/{id}
        get_resp = await ac.get(f"/api/v1/settings/templates/{template_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["category"] == "Artificial Intelligence"

        # PUT /api/v1/settings/templates/{id}
        put_resp = await ac.put(
            f"/api/v1/settings/templates/{template_id}",
            json={"title": "Distinguished AI Research Engineer"},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["title"] == "Distinguished AI Research Engineer"

        # DELETE /api/v1/settings/templates/{id}
        del_resp = await ac.delete(f"/api/v1/settings/templates/{template_id}")
        assert del_resp.status_code == 200

        # Verify 404
        get_deleted_resp = await ac.get(f"/api/v1/settings/templates/{template_id}")
        assert get_deleted_resp.status_code == 404

        # POST /api/v1/settings/templates/reset
        reset_resp = await ac.post("/api/v1/settings/templates/reset")
        assert reset_resp.status_code == 200
        assert len(reset_resp.json()) == 6


@pytest.mark.asyncio
async def test_job_templates_rendered_in_views(db_session):
    """Verifies that templates appear in screener, portfolio, and settings HTML views."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Screener view
        screener_resp = await ac.get("/screener")
        assert screener_resp.status_code == 200
        assert "FastAPI Backend Engineer" in screener_resp.text
        assert "load-jd-preset" in screener_resp.text
        assert "Configure Templates..." in screener_resp.text

        # 2. Portfolio view
        portfolio_resp = await ac.get("/portfolio")
        assert portfolio_resp.status_code == 200
        assert "FastAPI Backend Engineer" in portfolio_resp.text
        assert "load-portfolio-preset" in portfolio_resp.text

        # 3. Settings view
        settings_resp = await ac.get("/settings")
        assert settings_resp.status_code == 200
        assert "JD Templates" in settings_resp.text
        assert "templateModal" in settings_resp.text
        assert "Job Description Templates" in settings_resp.text
