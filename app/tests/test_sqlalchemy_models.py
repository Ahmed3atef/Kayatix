import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.core.database import create_engine_for_url
from app.models import (
    Base,
    Candidate,
    CandidateEvaluation,
    EvaluationCache,
    Job,
    JobTemplate,
    User,
    UserSettings,
    sync_all_models_to_database,
)


def test_models_are_sqlalchemy_classes():
    """Verifies that all models inherit from SQLAlchemy DeclarativeBase."""
    assert issubclass(User, Base)
    assert issubclass(Job, Base)
    assert issubclass(Candidate, Base)
    assert issubclass(JobTemplate, Base)
    assert issubclass(UserSettings, Base)
    assert issubclass(EvaluationCache, Base)
    assert CandidateEvaluation is EvaluationCache

    # Check table names registered in Base metadata
    registered_tables = list(Base.metadata.tables.keys())
    assert "users" in registered_tables
    assert "jobs" in registered_tables
    assert "candidates" in registered_tables
    assert "job_templates" in registered_tables
    assert "user_settings" in registered_tables
    assert "evaluation_cache" in registered_tables


def test_user_model_methods():
    """Verifies User model password hashing, verification, RBAC permissions, and serialization."""
    user = User(email="testuser@example.com", role="member", is_admin=False)
    user.set_password("SecurePassword999!")

    assert user.check_password("SecurePassword999!") is True
    assert user.check_password("WrongPassword") is False
    assert user.has_permission("can_manage_users") is False

    user.permissions = {"can_manage_users": True}
    assert user.has_permission("can_manage_users") is True

    user.is_admin = True
    assert user.has_permission("any_unlisted_action") is True

    d = user.to_dict()
    assert d["email"] == "testuser@example.com"
    assert "hashed_password" not in d


def test_job_and_candidate_models():
    """Verifies Job and Candidate models and skills parsing."""
    job = Job(title="FastAPI Engineer", description="Build APIs", required_skills=["FastAPI", "PostgreSQL"])
    assert job.skills_list == ["FastAPI", "PostgreSQL"]
    assert job.to_dict()["title"] == "FastAPI Engineer"

    cand = Candidate(
        name="John Doe",
        email="john@example.com",
        parsed_skills='["Python", "FastAPI"]',
        years_experience=4.5,
    )
    assert cand.skills_list == ["Python", "FastAPI"]
    assert cand.to_dict()["years_experience"] == 4.5


def test_user_settings_and_evaluation_cache():
    """Verifies UserSettings masking and EvaluationCache properties."""
    settings = UserSettings(database_url="postgresql://user:topsecret@neon.tech:5432/db")
    assert settings.database_type == "postgresql"
    assert "topsecret" not in settings.masked_database_url
    assert "••••••••" in settings.masked_database_url

    ev = EvaluationCache(
        request_hash="hash123",
        candidate_name="Jane",
        source_type="pdf_resume",
        match_score=85,
        provider_used="gemini",
        evaluation_json={"notes": "Strong candidate"},
    )
    assert ev.is_qualified is True
    assert ev.match_tier == "High"


@pytest.mark.asyncio
async def test_async_database_interactions():
    """
    Verifies that all models can be created and queried using an async SQLAlchemy session.
    """
    engine = create_engine_for_url("sqlite+aiosqlite:///:memory:")
    await sync_all_models_to_database(engine)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        new_job = Job(title="Async Architect", description="Expert with AsyncIO", required_skills=["Python"])
        session.add(new_job)
        await session.commit()

        stmt = select(Job).where(Job.title == "Async Architect")
        fetched = (await session.execute(stmt)).scalars().first()
        assert fetched is not None
        assert fetched.title == "Async Architect"

    await engine.dispose()
