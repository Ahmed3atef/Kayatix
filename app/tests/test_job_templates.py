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
async def test_job_templates_rendered_in_views(client):
    """Verifies that templates appear in screener, portfolio, and settings HTML views."""
    # 1. Screener view
    screener_resp = await client.get("/screener")
    assert screener_resp.status_code == 200
    assert "FastAPI Backend Engineer" in screener_resp.text
    assert "load-jd-preset" in screener_resp.text
    assert "Configure Templates..." in screener_resp.text

    # 2. Portfolio view
    portfolio_resp = await client.get("/portfolio")
    assert portfolio_resp.status_code == 200
    assert "FastAPI Backend Engineer" in portfolio_resp.text
    assert "load-portfolio-preset" in portfolio_resp.text

    # 3. Settings view
    settings_resp = await client.get("/settings")
    assert settings_resp.status_code == 200
    assert "JD Templates" in settings_resp.text
    assert "templateModal" in settings_resp.text
    assert "Job Description Templates" in settings_resp.text
    assert "syncSchemaDefaultsBtn" in settings_resp.text


@pytest.mark.asyncio
async def test_json_settings_schema_and_defaults_loading():
    """Verifies that the JSON defaults schema and file loaders work reliably."""
    from app.services.settings_service import (
        load_default_settings_schema,
        get_defaults_json_schema,
    )
    from app.schemas.payloads import AppDefaultsSchema

    # 1. Load schema
    schema = load_default_settings_schema()
    assert isinstance(schema, AppDefaultsSchema)
    assert len(schema.job_templates) >= 6
    assert schema.system_settings.project_name == "Kayatix - A.Y.A.T. Engine"
    assert schema.system_settings.rate_limit_rpm == 15

    # 2. Inspect generated JSON Schema
    json_schema = get_defaults_json_schema()
    assert isinstance(json_schema, dict)
    assert "doctype" in json_schema or "properties" in json_schema or "fields" in json_schema


@pytest.mark.asyncio
async def test_sync_global_defaults_insertion_and_modification_sync(db_session):
    """
    Verifies that sync_global_defaults performs:
    1. Global insertion of defaults when table is empty.
    2. Idempotent check (unchanged) on repeated runs.
    3. Detection and synchronization of modified data in schema into database.
    4. Preservation of custom user templates.
    """
    from app.services.settings_service import (
        sync_global_defaults,
        get_all_job_templates,
        create_job_template,
        load_default_settings_schema,
        save_default_settings_schema,
    )
    from app.models import JobTemplate
    from app.schemas.payloads import JobTemplateCreateRequest, JobTemplateSchema
    from sqlalchemy import delete

    # 1. Ensure empty state
    await db_session.execute(delete(JobTemplate))
    await db_session.commit()

    # 2. Run global insertion
    result1 = await sync_global_defaults(db_session)
    assert result1.templates_inserted >= 6
    assert result1.templates_updated == 0

    # 3. Run again without changes -> all unchanged
    result2 = await sync_global_defaults(db_session)
    assert result2.templates_inserted == 0
    assert result2.templates_updated == 0
    assert result2.templates_unchanged >= 6

    # 4. Create custom template created by user
    custom_req = JobTemplateCreateRequest(
        title="Custom Lead Bioinformatician",
        category="Life Sciences",
        description="Job Title: Lead Bioinformatician\nRequirements:\n- Genomics and Nextflow",
    )
    await create_job_template(db_session, custom_req)

    # 5. Modify the schema data (update an existing template and add a new template)
    clean_schema = load_default_settings_schema()
    # Create modified schema
    modified_schema = load_default_settings_schema()
    modified_templates = []
    for t in modified_schema.job_templates:
        if t.title == "FastAPI Backend Engineer":
            modified_templates.append(
                JobTemplateSchema(
                    title=t.title,
                    category="Platform Engineering",  # Changed category
                    description=t.description + "\n- Bonus: Antigravity Agentic AI experience.",  # Changed description
                )
            )
        else:
            modified_templates.append(t)

    # Add a brand new template to schema
    modified_templates.append(
        JobTemplateSchema(
            title="Embedded Robotics Kernel Developer",
            category="Hardware",
            description="Job Title: Embedded Robotics Kernel Developer\nRequirements:\n- Rust, RTOS, ARM Cortex",
        )
    )

    modified_schema.job_templates = modified_templates
    save_default_settings_schema(modified_schema)

    try:
        # 6. Run sync_global_defaults -> should update modified and insert new!
        result3 = await sync_global_defaults(db_session)
        assert result3.templates_inserted == 1  # "Embedded Robotics Kernel Developer" inserted
        assert result3.templates_updated >= 1   # "FastAPI Backend Engineer" updated

        # Verify DB records
        all_templates = await get_all_job_templates(db_session)
        t_dict = {t.title: t for t in all_templates}

        # Check updated template
        fastapi_t = t_dict["FastAPI Backend Engineer"]
        assert fastapi_t.category == "Platform Engineering"
        assert "Antigravity Agentic AI experience" in fastapi_t.description

        # Check inserted new template
        assert "Embedded Robotics Kernel Developer" in t_dict

        # Check preserved custom user template
        assert "Custom Lead Bioinformatician" in t_dict

    finally:
        # Restore defaults.json and db back to clean original schema to avoid test leakage
        save_default_settings_schema(clean_schema)
        await reset_default_job_templates(db_session)


@pytest.mark.asyncio
async def test_defaults_schema_endpoints(db_session):
    """Verifies REST API endpoints for JSON settings schema and sync."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. GET /api/v1/settings/schema/defaults
        get_resp = await ac.get("/api/v1/settings/schema/defaults")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "json_schema" in data
        assert "defaults" in data
        assert len(data["defaults"]["job_templates"]) >= 6

        # 2. POST /api/v1/settings/schema/defaults/sync
        sync_resp = await ac.post("/api/v1/settings/schema/defaults/sync")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert "templates_inserted" in sync_data
        assert "templates_updated" in sync_data
        assert "templates_unchanged" in sync_data
        assert "message" in sync_data

        # 3. PUT /api/v1/settings/schema/defaults
        schema_payload = data["defaults"]
        put_resp = await ac.put("/api/v1/settings/schema/defaults", json=schema_payload)
        assert put_resp.status_code == 200
        put_data = put_resp.json()
        assert "message" in put_data


@pytest.mark.asyncio
async def test_frappe_doctype_schemas():
    """
    Verifies that Frappe DocType schemas:
    1. Load correctly from the dedicated models/ folder.
    2. Contain standard Frappe fields: doctype, field_order, fields, permissions.
    3. Are exposed via the REST API endpoint /api/v1/settings/schema/doctype/{doctype_name}.
    """
    from app.services.settings_service import get_frappe_doctype_schema

    job_schema = get_frappe_doctype_schema("job_template")
    assert isinstance(job_schema, dict)
    assert job_schema.get("doctype") == "DocType"
    assert job_schema.get("name") == "Job Template"
    assert "field_order" in job_schema
    assert "fields" in job_schema
    fieldnames = [f["fieldname"] for f in job_schema["fields"]]
    assert "title" in fieldnames
    assert "category" in fieldnames
    assert "description" in fieldnames

    settings_schema = get_frappe_doctype_schema("user_settings")
    assert isinstance(settings_schema, dict)
    assert settings_schema.get("doctype") == "DocType"
    assert settings_schema.get("issingle") == 1

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/settings/schema/doctype/job_template")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("doctype") == "DocType"
        assert data.get("name") == "Job Template"


@pytest.mark.asyncio
async def test_timestamp_change_detection_and_reverse_sync(db_session):
    """
    Verifies that:
    1. Changing modified_timestamp in schema file triggers synchronization into database.
    2. Reverse sync updates modified_timestamp to a fresh ISO timestamp and writes to JSON file.
    3. Export endpoint returns status 200 with new timestamp.
    """
    from app.services.settings_service import (
        load_default_settings_schema,
        save_default_settings_schema,
        sync_global_defaults,
    )

    clean_templates_schema = load_default_settings_schema()

    try:
        # 1. Modify timestamp in fixtures/job_template.json
        new_timestamp = "2026-10-16T22:30:00Z"
        test_schema = load_default_settings_schema()
        test_schema.modified_timestamp = new_timestamp
        save_default_settings_schema(test_schema)

        # 2. Run sync_global_defaults -> should detect timestamp change
        res = await sync_global_defaults(db_session)
        assert res.settings_synced is True

        # Verify DB has new timestamp
        from app.services.settings_service import get_or_create_user_settings
        settings_rec = await get_or_create_user_settings(db_session)
        assert settings_rec.job_templates_schema_timestamp == new_timestamp

        # 3. Test REST endpoint for templates export (reverse sync)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            t_export_resp = await ac.post("/api/v1/settings/schema/templates/export")
            assert t_export_resp.status_code == 200
            t_export_data = t_export_resp.json()
            assert t_export_data["modified_timestamp"] is not None

    finally:
        save_default_settings_schema(clean_templates_schema)
        await sync_global_defaults(db_session, force=True)



