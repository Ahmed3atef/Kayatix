"""
Candidate sourcing and LinkedIn X-Ray schemas.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


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


__all__ = [
    "XRaySearchRequest",
    "XRayProfileItem",
]
