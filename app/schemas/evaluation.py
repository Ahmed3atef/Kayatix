"""
Candidate evaluation and interview question schemas.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


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


__all__ = [
    "InterviewQuestionSchema",
    "CandidateEvaluationResult",
    "EvaluationAPIResponse",
]
