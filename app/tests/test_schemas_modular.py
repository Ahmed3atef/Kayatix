import pytest
from app.schemas.evaluation import CandidateEvaluationResult, EvaluationAPIResponse, InterviewQuestionSchema
from app.schemas.job_template import JobTemplateCreateRequest, JobTemplateResponse, JobTemplateSchema
from app.schemas.settings import AppDefaultsSchema, DatabaseValidationResponse, UserSettingsResponse
from app.schemas.sourcing import XRayProfileItem, XRaySearchRequest
from app.schemas.user import AuthTokenResponse, UserCreateRequest, UserResponse
from app.schemas import (
    CandidateEvaluationResult as CentralEval,
    JobTemplateResponse as CentralJob,
    UserSettingsResponse as CentralSettings,
    UserResponse as CentralUser,
)
from app.schemas.payloads import (
    CandidateEvaluationResult as PayloadEval,
    JobTemplateResponse as PayloadJob,
    UserSettingsResponse as PayloadSettings,
    UserResponse as PayloadUser,
)


def test_modular_schema_imports_and_instantiation():
    """Verifies that schemas can be imported from modular files and instantiated."""
    # Evaluation
    q = InterviewQuestionSchema(
        category="Technical",
        question="How does asyncpg connection pooling work?",
        target_area="Database Optimization",
        expected_answer_criteria="Pre-ping, max overflow, and disposal.",
    )
    eval_res = CandidateEvaluationResult(
        candidate_name="Alice Smith",
        match_percentage=92,
        executive_summary="Excellent backend engineer",
        estimated_years_experience=6.0,
        tailored_interview_questions=[q],
    )
    assert eval_res.match_percentage == 92
    assert eval_res.years_of_experience == 6.0

    # Job Template
    job_req = JobTemplateCreateRequest(
        title="Staff Engineer",
        category="Engineering",
        description="Lead backend architecture and distributed systems.",
    )
    assert job_req.title == "Staff Engineer"

    # Sourcing
    xray = XRaySearchRequest(
        job_title="FastAPI Developer",
        required_skills=["Python", "FastAPI"],
        location="Berlin",
    )
    assert xray.location == "Berlin"

    # User
    user_res = UserResponse(
        id=1,
        email="test@example.com",
        full_name="Tester",
        role="admin",
        is_active=True,
        is_admin=True,
    )
    assert user_res.id == 1

    # Verify central and payload exports point to identical classes
    assert CentralEval is CandidateEvaluationResult is PayloadEval
    assert CentralJob is JobTemplateResponse is PayloadJob
    assert CentralSettings is UserSettingsResponse is PayloadSettings
    assert CentralUser is UserResponse is PayloadUser


def test_senior_hr_evaluation_result_validation():
    """Verifies Senior HR evaluation schema validators, clamping, and hiring recommendation defaults."""
    res = CandidateEvaluationResult(
        candidate_name="John Senior",
        match_percentage="87.6",  # string float input
        estimated_years_experience="7.25",  # string float input
        executive_summary="[STRONG HIRE] 7+ years backend experience...",
        hiring_recommendation="Strong Hire",
    )
    assert res.match_percentage == 88
    assert res.estimated_years_experience == 7.2
    assert res.hiring_recommendation == "Strong Hire"

    # Out of bounds clamping
    clamped_high = CandidateEvaluationResult(match_percentage=150)
    assert clamped_high.match_percentage == 100

    clamped_low = CandidateEvaluationResult(match_percentage=-20)
    assert clamped_low.match_percentage == 0
