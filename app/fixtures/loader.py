"""
Fixture loading and database seeding engine for Kayatix.
Reads entity fixtures from the fixtures/ directory and populates / synchronizes database tables.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import JobTemplate, UserSettings

logger = logging.getLogger("kayatix.fixtures")
FIXTURES_DIR = Path(__file__).resolve().parent


def get_fixture_path(name: str) -> Path:
    """Returns absolute path to a fixture JSON file in the fixtures/ directory."""
    filename = name if name.endswith(".json") else f"{name}.json"
    return FIXTURES_DIR / filename


def read_fixture(name: str) -> List[Dict[str, Any]]:
    """Reads a fixture JSON file and returns a list of records."""
    path = get_fixture_path(name)
    if not path.exists():
        logger.warning(f"[Fixtures] Fixture file not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    return data["data"]
                if "records" in data and isinstance(data["records"], list):
                    return data["records"]
                return [data]
    except Exception as e:
        logger.error(f"[Fixtures] Error reading fixture {path}: {e}")
    return []


async def seed_job_templates_from_fixture(
    db: AsyncSession,
    force_reload: bool = False,
) -> Dict[str, Any]:
    """
    Seeds default JobTemplate records from fixtures/job_template.json into the database.
    If force_reload is True, clears existing default templates before inserting.
    """
    records = read_fixture("job_template")
    if not records:
        return {"status": "skipped", "message": "No job template fixtures found", "inserted": 0, "updated": 0}

    if force_reload:
        await db.execute(delete(JobTemplate))
        await db.commit()

    # Query existing templates
    stmt = select(JobTemplate)
    res = await db.execute(stmt)
    existing = {t.title.strip().lower(): t for t in res.scalars().all()}

    inserted = 0
    updated = 0

    for item in records:
        title = item.get("title", "").strip()
        if not title:
            continue
        category = item.get("category", "General").strip()
        description = item.get("description", "").strip()

        key = title.lower()
        if key not in existing:
            new_tmpl = JobTemplate(
                title=title,
                category=category,
                description=description,
            )
            db.add(new_tmpl)
            inserted += 1
        else:
            tmpl = existing[key]
            changed = False
            if tmpl.category != category:
                tmpl.category = category
                changed = True
            if tmpl.description != description:
                tmpl.description = description
                changed = True
            if changed:
                updated += 1

    await db.commit()
    logger.info(f"[Fixtures] Seeded JobTemplates: {inserted} inserted, {updated} updated.")
    return {
        "status": "ok",
        "inserted": inserted,
        "updated": updated,
        "total": len(records),
    }


async def seed_user_settings_from_fixture(db: AsyncSession) -> Optional[UserSettings]:
    """
    Seeds initial UserSettings from fixtures/user_settings.json into the database if missing.
    """
    records = read_fixture("user_settings")
    fixture_data: Dict[str, Any] = records[0] if records else {}

    stmt = select(UserSettings).limit(1)
    res = await db.execute(stmt)
    settings_rec = res.scalars().first()

    if not settings_rec:
        settings_rec = UserSettings(
            project_name=fixture_data.get("project_name", "Kayatix - A.Y.A.T. Engine"),
            version=fixture_data.get("version", "1.0.0"),
            subscription_tier=fixture_data.get("subscription_tier", "standard"),
            evaluation_mode=fixture_data.get("evaluation_mode", "llm_cascade"),
            rate_limit_rpm=fixture_data.get("rate_limit_rpm", 15),
        )
        db.add(settings_rec)
        await db.commit()
        await db.refresh(settings_rec)
        logger.info("[Fixtures] Created initial UserSettings from fixture.")
    return settings_rec


async def load_fixtures_to_database(
    db: AsyncSession,
    force_reload: bool = False,
) -> Dict[str, Any]:
    """
    Full fixture loader: fills the database with all system fixtures (JobTemplates, UserSettings).
    """
    settings = await seed_user_settings_from_fixture(db)
    tmpl_res = await seed_job_templates_from_fixture(db, force_reload=force_reload)

    return {
        "status": "ok",
        "settings_initialized": settings is not None,
        "job_templates": tmpl_res,
    }
