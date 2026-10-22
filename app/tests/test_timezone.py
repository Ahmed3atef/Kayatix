"""
Unit and integration tests for Country Timezone Configuration, Localized Logging,
and Database Insertion Timestamps in Kayatix.
"""

from datetime import datetime, timezone
import logging
import os
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select

from app.core.config import Settings, resolve_timezone
from app.core.timezone import (
    configure_timezone_logging,
    format_localized_time,
    get_app_timezone,
    get_current_aware_time,
    get_current_time,
    get_timezone_obj,
    TimezoneFormatter,
)
from app.models import (
    Candidate,
    CandidateEvaluation,
    EvaluationCache,
    Job,
    JobTemplate,
    User,
    UserSettings,
    get_current_time as model_get_current_time,
    utc_now,
)
from app.services.settings_service import update_user_settings
from app.schemas.settings import UserSettingsUpdateRequest


def test_resolve_timezone_resolution_order(tmp_path):
    """Verifies strict priority resolution: .env -> os.environ -> UTC fallback."""
    # 1. Fallback when neither is set
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_timezone(env_path=str(tmp_path / "non_existent.env")) == "UTC"

    # 2. System environment variable fallback
    with patch.dict(os.environ, {"TIMEZONE": "Asia/Riyadh"}):
        assert resolve_timezone(env_path=str(tmp_path / "non_existent.env")) == "Asia/Riyadh"

    with patch.dict(os.environ, {"APP_TIMEZONE": "Europe/London"}):
        assert resolve_timezone(env_path=str(tmp_path / "non_existent.env")) == "Europe/London"

    # 3. .env file priority over os.environ
    env_file = tmp_path / ".env.test"
    env_file.write_text('TIMEZONE="Africa/Cairo"\n', encoding="utf-8")
    with patch.dict(os.environ, {"TIMEZONE": "UTC"}):
        assert resolve_timezone(env_path=str(env_file)) == "Africa/Cairo"


def test_get_timezone_obj_and_graceful_fallback():
    """Verifies that invalid or corrupted timezones fall back to UTC cleanly."""
    cairo_tz = get_timezone_obj("Africa/Cairo")
    assert str(cairo_tz) == "Africa/Cairo"

    utc_tz = get_timezone_obj("UTC")
    assert str(utc_tz) == "UTC"

    # Invalid timezone must fall back to UTC without throwing
    invalid_tz = get_timezone_obj("NonExistent/Invalid_Country_Timezone")
    assert str(invalid_tz) == "UTC"

    # Empty string falls back to UTC
    empty_tz = get_timezone_obj("")
    assert str(empty_tz) == "UTC"


def test_get_current_time_reflects_country_timezone():
    """
    Verifies that get_current_time returns a naive datetime matching the country's local time,
    ensuring 100% database compatibility with asyncpg / PostgreSQL and SQLite.
    """
    cairo_tz = ZoneInfo("Africa/Cairo")
    cairo_now = get_current_time(cairo_tz)
    assert cairo_now.tzinfo is None

    # Compare with aware time
    cairo_aware = get_current_aware_time(cairo_tz)
    assert cairo_aware.tzinfo is not None
    assert cairo_now.hour == cairo_aware.hour
    assert cairo_now.day == cairo_aware.day

    # Verify alias compatibility
    assert utc_now() is not None
    assert model_get_current_time() is not None


def test_timezone_formatter_logging():
    """Verifies that TimezoneFormatter formats record timestamps using the country timezone."""
    formatter = TimezoneFormatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        tz_name="Africa/Cairo",
    )
    # Create dummy LogRecord
    record = logging.LogRecord(
        name="test.tz",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Testing localized logger timestamp",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "Testing localized logger timestamp" in formatted

    # Check time output
    expected_cairo_time = datetime.fromtimestamp(record.created, tz=ZoneInfo("Africa/Cairo")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert expected_cairo_time in formatted


def test_configure_timezone_logging():
    """Verifies root logger configuration with TimezoneFormatter."""
    handler = configure_timezone_logging(level=logging.DEBUG)
    assert isinstance(handler.formatter, TimezoneFormatter)
    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.asyncio
async def test_database_insertions_record_country_time(db_session):
    """
    Verifies that inserting models (Candidate, Job, User, JobTemplate)
    saves created_at timestamps matching the configured country timezone.
    """
    from app.core.config import settings

    original_tz = settings.TIMEZONE
    try:
        settings.TIMEZONE = "Africa/Cairo"
        cairo_tz = ZoneInfo("Africa/Cairo")
        before_insert = datetime.now(cairo_tz).replace(tzinfo=None)

        # 1. Candidate model
        candidate = Candidate(
            name="Ahmed Test",
            email="ahmed.test@example.com",
            parsed_skills=["Python", "FastAPI"],
            years_experience=6.0,
        )
        db_session.add(candidate)

        # 2. Job model
        job = Job(
            title="Senior Backend Engineer",
            description="FastAPI, PostgreSQL, AsyncIO",
            required_skills=["Python", "FastAPI"],
        )
        db_session.add(job)

        # 3. JobTemplate model
        template = JobTemplate(
            title="DevOps Specialist",
            category="Infrastructure",
            description="Terraform, Kubernetes, CI/CD",
        )
        db_session.add(template)

        # 4. User model
        user = User(
            email="hr_manager@kayatix.local",
            hashed_password="dummy_hash_123",
            full_name="HR Manager",
            role="recruiter",
        )
        db_session.add(user)

        await db_session.commit()
        await db_session.refresh(candidate)
        await db_session.refresh(job)
        await db_session.refresh(template)
        await db_session.refresh(user)

        after_insert = datetime.now(cairo_tz).replace(tzinfo=None)

        # Candidate timestamp validation
        assert candidate.created_at is not None
        assert candidate.created_at >= before_insert.replace(microsecond=0)
        assert candidate.created_at <= after_insert

        # Job timestamp validation
        assert job.created_at is not None
        assert job.created_at >= before_insert.replace(microsecond=0)

        # Template timestamp validation
        assert template.created_at is not None
        assert template.updated_at is not None

        # User timestamp validation
        assert user.created_at is not None
        assert user.updated_at is not None

    finally:
        settings.TIMEZONE = original_tz


@pytest.mark.asyncio
async def test_update_timezone_in_user_settings(db_session):
    """
    Verifies that updating raw env_content with TIMEZONE correctly updates settings.TIMEZONE.
    """
    from app.core.config import settings

    raw_env = (
        'TIMEZONE="Asia/Dubai"\n'
        'RATE_LIMIT_RPM=30\n'
    )
    req = UserSettingsUpdateRequest(env_content=raw_env)
    res = await update_user_settings(req, db_session)

    assert settings.TIMEZONE == "Asia/Dubai"
    assert get_app_timezone() == ZoneInfo("Asia/Dubai")
