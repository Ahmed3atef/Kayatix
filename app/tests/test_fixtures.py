import json
from pathlib import Path
import pytest
from app.core.database import create_engine_for_url
from app.fixtures.loader import (
    FIXTURES_DIR,
    get_fixture_path,
    load_fixtures_to_database,
    read_fixture,
    seed_job_templates_from_fixture,
    seed_user_settings_from_fixture,
)
from app.models import Base, JobTemplate, UserSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def test_fixtures_files_exist_and_valid():
    """Verifies that all fixture files exist in fixtures/ and are valid JSON."""
    assert FIXTURES_DIR.exists()
    assert (FIXTURES_DIR / "job_template.json").exists()
    assert (FIXTURES_DIR / "user_settings.json").exists()
    assert not (FIXTURES_DIR / "default_job_templates.json").exists()

    # Verify job_template.json
    job_records = read_fixture("job_template")
    assert isinstance(job_records, list)
    assert len(job_records) >= 6
    for item in job_records:
        assert "title" in item
        assert "category" in item
        assert "description" in item

    # Verify user_settings.json
    settings_records = read_fixture("user_settings")
    assert isinstance(settings_records, list)
    assert len(settings_records) >= 1
    assert "project_name" in settings_records[0]


@pytest.mark.asyncio
async def test_load_fixtures_to_database():
    """
    Verifies that load_fixtures_to_database seeds job templates and user settings
    into an in-memory SQLite database.
    """
    engine = create_engine_for_url("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        res = await load_fixtures_to_database(db, force_reload=True)
        assert res["status"] == "ok"
        assert res["settings_initialized"] is True
        assert res["job_templates"]["inserted"] >= 6

    await engine.dispose()
