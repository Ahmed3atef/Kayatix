"""
Candidate evaluation and interview question schemas.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


class InterviewQuestionSchema(BaseModel):
    category: str = Field(description="Must be one of: Technical Deep-Dive, Behavioral (STAR), System Design & Architecture, or Gap Verification")
    question: str = Field(description="Incisive, challenging question tailored to the candidate's specific projects, claims, or identified gaps")
    target_area: str = Field(description="The exact skill, project claim, or potential gap being tested")
    expected_answer_criteria: str = Field(description="Concrete technical points, architectural patterns, or behavioral signals a strong candidate should mention")


class CandidateEvaluationResult(BaseModel):
    candidate_name: Optional[str] = Field(default="Unknown Candidate", description="Extracted full name of the candidate")
    match_percentage: int = Field(ge=0, le=100, description="Strict, calibrated merit match score from 0 to 100 based on the 100-point Senior HR rubric")
    executive_summary: str = Field(default="", description="2-4 sentence high-signal executive assessment starting with a hiring recommendation verdict [STRONG HIRE | PROCEED - TECH SCREEN | BORDERLINE | REJECT]")
    estimated_years_experience: float = Field(default=0.0, ge=0.0, description="Total calculated years of relevant commercial/professional experience (excluding non-relevant work)")
    matched_skills: List[str] = Field(default_factory=list, description="Skills explicitly verified in candidate project work or commercial experience that match the JD")
    missing_critical_skills: List[str] = Field(default_factory=list, description="Mandatory core JD requirements absent or unverified in the candidate profile")
    detected_projects_and_impact: List[str] = Field(default_factory=list, description="Key technical projects, architectures, or quantifiable metrics achieved (STAR format)")
    red_flags_and_gaps: List[str] = Field(default_factory=list, description="Unexplained timeline gaps (>6 mos), high hopping velocity (<9 mos/role), or unverified buzzword claims")
    tailored_interview_questions: List[InterviewQuestionSchema] = Field(default_factory=list, description="5 to 7 custom interview questions across Technical, Behavioral, and Gap Verification")
    hiring_recommendation: Optional[str] = Field(
        default="Proceed (Technical Screen)",
        description="One of: 'Strong Hire', 'Proceed (Technical Screen)', 'Borderline (Phone Screen First)', or 'Reject / Not Recommended'"
    )

    @field_validator("match_percentage", mode="before")
    @classmethod
    def clamp_match_percentage(cls, v: Any) -> int:
        try:
            val = int(round(float(v)))
            return max(0, min(100, val))
        except Exception:
            return 50

    @field_validator("estimated_years_experience", mode="before")
    @classmethod
    def clean_years_experience(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, round(val, 1))
        except Exception:
            return 0.0

    @field_validator("hiring_recommendation", mode="before")
    @classmethod
    def clean_recommendation(cls, v: Any) -> str:
        if v and isinstance(v, str) and v.strip():
            return v.strip()
        return "Proceed (Technical Screen)"

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
