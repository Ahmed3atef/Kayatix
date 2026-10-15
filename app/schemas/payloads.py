from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class InterviewQuestionSchema(BaseModel):
    category: str = Field(description="Must be one of: Technical, Behavioral, System Design, or Gap-Verification")
    question: str = Field(description="Direct, challenging question tailored to the candidate's specific projects or gaps")
    target_area: str = Field(description="The exact skill or resume claim being tested")
    expected_answer_criteria: str = Field(description="Concrete technical points or behavioral signals a strong candidate should mention")


class CandidateEvaluationResult(BaseModel):
    candidate_name: Optional[str] = Field(default="Unknown Candidate", description="Extracted full name")
    match_percentage: int = Field(ge=0, le=100, description="Strict merit-based match score from 0 to 100")
    executive_summary: str = Field(description="2-3 sentence objective assessment of candidate fit")
    estimated_years_experience: float = Field(ge=0.0, description="Total calculated years of relevant professional experience")
    matched_skills: List[str] = Field(default_factory=list, description="Skills explicitly verified in the candidate profile that match the JD")
    missing_critical_skills: List[str] = Field(default_factory=list, description="Required JD skills completely absent from the candidate profile")
    detected_projects_and_impact: List[str] = Field(default_factory=list, description="Key technical projects, architectures, or quantifiable metrics achieved")
    red_flags_and_gaps: List[str] = Field(default_factory=list, description="Unexplained timeline gaps, vague claims without proof, or frequent job hopping")
    tailored_interview_questions: List[InterviewQuestionSchema] = Field(default_factory=list, description="5 to 7 custom interview questions")


class EvaluationAPIResponse(BaseModel):
    cached: bool
    provider_used: str
    analysis: CandidateEvaluationResult


class XRaySearchRequest(BaseModel):
    job_title: str = Field(..., examples=["Senior FastAPI Backend Engineer"])
    required_skills: List[str] = Field(..., examples=["Python", "PostgreSQL", "Docker"])
    location: str = Field(..., examples=["Cairo", "Egypt"])
    max_results: int = Field(default=5, ge=1, le=10)
    job_description_for_ranking: Optional[str] = None


class XRayProfileItem(BaseModel):
    full_title: str
    linkedin_url: str
    snippet: str
    ai_quick_fit_score: Optional[int] = None
    ai_outreach_message: Optional[str] = None


class UserSettingsResponse(BaseModel):
    gemini_api_key_configured: bool
    groq_api_key_configured: bool
    openrouter_api_key_configured: bool
    google_cse_api_key_configured: bool
    google_cse_cx_id_configured: bool
    subscription_tier: str = "standard"
    evaluation_mode: str = "hybrid"
    rate_limit_rpm: int = 15
    env_content: Optional[str] = None
    updated_at: Optional[str] = None


class UserSettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    google_cse_api_key: Optional[str] = None
    google_cse_cx_id: Optional[str] = None
    subscription_tier: Optional[str] = None
    evaluation_mode: Optional[str] = None
    rate_limit_rpm: Optional[int] = None
    env_content: Optional[str] = None




class ProviderValidationStatus(BaseModel):
    status: str  # "valid", "invalid", "unconfigured"
    message: str
    model_tested: Optional[str] = None


class SettingsValidationResponse(BaseModel):
    gemini: ProviderValidationStatus
    groq: ProviderValidationStatus
    openrouter: ProviderValidationStatus
    google_cse: ProviderValidationStatus
    overall_ready: bool


class JobTemplateCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    category: str = Field(default="General", max_length=100)
    description: str = Field(..., min_length=10)


class JobTemplateUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, min_length=10)


class JobTemplateResponse(BaseModel):
    id: int
    title: str
    category: str
    description: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


