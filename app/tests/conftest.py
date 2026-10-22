import os
from collections.abc import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set dummy environment keys for testing before importing settings
os.environ["GEMINI_API_KEY"] = "mock_gemini_key"
os.environ["GROQ_API_KEY"] = "mock_groq_key"
os.environ["OLLAMA_API_KEY"] = "mock_ollama_key"
os.environ["GOOGLE_CSE_CX_ID"] = "mock_cse_cx"

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.schemas.payloads import CandidateEvaluationResult, InterviewQuestionSchema
from app.services.auth_service import create_access_token

# Test in-memory SQLite engine
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function", autouse=True)
def isolate_test_database():
    import app.core.database as app_db
    original_session_local = app_db.AsyncSessionLocal
    original_db_url = settings.DATABASE_URL
    app_db.AsyncSessionLocal = TestSessionLocal
    settings.DATABASE_URL = TEST_DATABASE_URL
    yield
    app_db.AsyncSessionLocal = original_session_local
    settings.DATABASE_URL = original_db_url


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Create a default test admin user
    test_user = User(
        email="test_admin@kayatix.local",
        role="admin",
        is_admin=True,
        is_active=True,
        full_name="Test Administrator",
    )
    test_user.set_password("AdminPass123!")
    db_session.add(test_user)
    await db_session.commit()
    await db_session.refresh(test_user)

    token = create_access_token({"sub": str(test_user.id), "email": test_user.email, "role": test_user.role})

    transport = ASGITransport(app=app)
    cookies = {"kayatix_token": token}
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def sample_candidate_evaluation() -> CandidateEvaluationResult:
    return CandidateEvaluationResult(
        candidate_name="Jane Doe",
        match_percentage=92,
        executive_summary="Highly skilled engineer with strong asynchronous Python and FastAPI experience.",
        estimated_years_experience=6.5,
        matched_skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
        missing_critical_skills=["Kubernetes"],
        detected_projects_and_impact=[
            "Architected high-throughput async data pipeline processing 10k req/sec",
            "Migrated monolithic architecture to microservices with zero downtime",
        ],
        red_flags_and_gaps=[],
        tailored_interview_questions=[
            InterviewQuestionSchema(
                category="Technical",
                question="How do you handle connection pooling and transaction rollbacks with async SQLAlchemy?",
                target_area="SQLAlchemy async ORM",
                expected_answer_criteria="Should explain async context manager sessions, AsyncSessionLocal, and expire_on_commit.",
            ),
            InterviewQuestionSchema(
                category="System Design",
                question="Describe how you would design a rate-limiting circuit breaker for upstream AI APIs.",
                target_area="High Availability Architecture",
                expected_answer_criteria="Mentions exponential backoff, token buckets, and fallback queues.",
            ),
        ],
    )
