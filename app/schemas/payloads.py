from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl


class InterviewQuestionSchema(BaseModel):
    category: str = Field(description="Must be one of: Technical, Behavioral, System Design, or Gap-Verification")
    question: str = Field(description="Direct, challenging question tailored to the candidate's specific projects or gaps")
    target_area: str = Field(description="The exact skill or resume claim being tested")
    expected_answer_criteria: str = Field(description="Concrete technical points or behavioral signals a strong candidate should mention")


class CandidateEvaluationResult(BaseModel):
    candidate_name: Optional[str] = Field(default="Unknown Candidate", description="Extracted full name")
    match_percentage: int = Field(ge=0, le=100, description="Strict merit-based match score from 0 to 100")
    executive_summary: str = Field(default="", description="2-3 sentence objective assessment of candidate fit")
    estimated_years_experience: float = Field(default=0.0, ge=0.0, description="Total calculated years of relevant professional experience")
    matched_skills: List[str] = Field(default_factory=list, description="Skills explicitly verified in the candidate profile that match the JD")
    missing_critical_skills: List[str] = Field(default_factory=list, description="Required JD skills completely absent from the candidate profile")
    detected_projects_and_impact: List[str] = Field(default_factory=list, description="Key technical projects, architectures, or quantifiable metrics achieved")
    red_flags_and_gaps: List[str] = Field(default_factory=list, description="Unexplained timeline gaps, vague claims without proof, or frequent job hopping")
    tailored_interview_questions: List[InterviewQuestionSchema] = Field(default_factory=list, description="5 to 7 custom interview questions")

    @property
    def years_of_experience(self) -> float:
        return self.estimated_years_experience

    @property
    def red_flags(self) -> List[str]:
        return self.red_flags_and_gaps


class EvaluationAPIResponse(BaseModel):
    cached: bool
    provider_used: str
    analysis: CandidateEvaluationResult
    extraction_method: Optional[str] = "cloud_ocr"


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
    ollama_api_key_configured: bool
    ollama_base_url: Optional[str] = "https://ollama.com/v1"
    google_cse_cx_id_configured: bool
    subscription_tier: str = "standard"
    evaluation_mode: str = "llm_cascade"
    rate_limit_rpm: int = 15
    database_url: Optional[str] = None
    masked_database_url: Optional[str] = None
    database_type: str = "postgresql"
    env_content: Optional[str] = None
    updated_at: Optional[str] = None
    provider_health: dict[str, str] = Field(default_factory=dict)


class UserSettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    ollama_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    google_cse_cx_id: Optional[str] = None
    subscription_tier: Optional[str] = None
    evaluation_mode: Optional[str] = None
    rate_limit_rpm: Optional[int] = None
    database_url: Optional[str] = None
    env_content: Optional[str] = None


class DatabaseValidationRequest(BaseModel):
    database_url: Optional[str] = None


class DatabaseValidationResponse(BaseModel):
    status: str  # "valid", "invalid"
    message: str
    database_type: str  # "sqlite", "postgresql"
    normalized_url: Optional[str] = None
    latency_ms: Optional[float] = None
    tables_found: List[str] = []




class ProviderValidationStatus(BaseModel):
    status: str  # "valid", "invalid", "unconfigured"
    message: str
    model_tested: Optional[str] = None


class SettingsValidationResponse(BaseModel):
    gemini: ProviderValidationStatus
    groq: ProviderValidationStatus
    ollama: ProviderValidationStatus
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


class JobTemplateSchema(BaseModel):
    title: str = Field(..., min_length=2, max_length=255, description="Official job title")
    category: str = Field(default="General", max_length=100, description="Department or job category")
    description: str = Field(..., min_length=10, description="Full job description requirements and specs")


class SystemSettingsDefaultsSchema(BaseModel):
    project_name: str = Field(default="Kayatix - A.Y.A.T. Engine", description="Default project or platform name")
    version: str = Field(default="1.0.0", description="Default application version")
    subscription_tier: str = Field(default="standard", description="Default subscription tier")
    evaluation_mode: str = Field(default="llm_cascade", description="Default candidate evaluation mode")
    rate_limit_rpm: int = Field(default=15, ge=1, le=1000, description="Default rate limit in requests per minute")


class AppDefaultsSchema(BaseModel):
    version: str = Field(default="1.0.0", description="Schema specification version")
    modified_timestamp: Optional[str] = Field(
        default="2026-10-16T19:00:00Z",
        description="ISO timestamp marking when the schema file was last modified"
    )
    system_settings: SystemSettingsDefaultsSchema = Field(
        default_factory=SystemSettingsDefaultsSchema,
        description="System configuration defaults"
    )
    job_templates: List[JobTemplateSchema] = Field(
        default_factory=list,
        description="List of standard job description templates"
    )


class DefaultsSyncResult(BaseModel):
    templates_inserted: int = Field(default=0, description="Number of new templates inserted into database")
    templates_updated: int = Field(default=0, description="Number of existing templates updated with modified schema data")
    templates_unchanged: int = Field(default=0, description="Number of templates already in sync")
    settings_synced: bool = Field(default=False, description="Whether system settings defaults were updated in database")
    instructions_synced: bool = Field(default=False, description="Whether RAG & AI instructions were synced into database")
    message: str = Field(default="", description="Human-readable synchronization summary message")


class DefaultsSchemaResponse(BaseModel):
    json_schema: Dict[str, Any] = Field(description="Standard JSON Schema specification")
    defaults: AppDefaultsSchema = Field(description="Active default data payload")


class RAGAIInstructionSchema(BaseModel):
    name: str = Field(default="default_evaluator", description="Unique identifier for the evaluator prompt suite")
    description: Optional[str] = Field(None, description="Overview of the prompt persona and evaluation objectives")
    modified_timestamp: Optional[str] = Field(
        default="2026-10-16T19:00:00Z",
        description="ISO timestamp marking when instructions were last modified"
    )
    system_instruction: str = Field(..., min_length=20, description="Principal Bar Raiser system instruction with CoT guidelines")
    rag_prompt_template: str = Field(..., min_length=20, description="RAG candidate evidence matrix formatting template")


class RAGAIInstructionResponse(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    modified_timestamp: Optional[str] = None
    system_instruction: str
    rag_prompt_template: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None




