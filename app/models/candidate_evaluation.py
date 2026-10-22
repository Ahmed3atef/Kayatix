"""
EvaluationCache / CandidateEvaluation SQLAlchemy model caching evaluation scores and logs.
"""

from datetime import datetime
from typing import Any, Dict
from sqlalchemy import Column, DateTime, Integer, JSON, String
from app.models.base import Base, utc_now


class EvaluationCache(Base):
    """
    SQLAlchemy model caching AI evaluations, candidate match scores, and audit logs.
    """
    __tablename__ = "evaluation_cache"

    id = Column(Integer, primary_key=True, index=True)
    request_hash = Column(String(64), unique=True, index=True, nullable=False)
    candidate_name = Column(String(255), nullable=True)
    source_type = Column(String(50), nullable=False)  # "pdf_resume", "portfolio_url", "xray_snippet"
    match_score = Column(Integer, nullable=False)
    provider_used = Column(String(100), nullable=False)
    evaluation_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    @property
    def is_qualified(self) -> bool:
        """Determines qualification threshold (match_score >= 70)."""
        return self.match_score >= 70

    @property
    def match_tier(self) -> str:
        """Categorizes score into High / Medium / Low match tiers."""
        if self.match_score >= 80:
            return "High"
        if self.match_score >= 60:
            return "Medium"
        return "Low"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes evaluation record to dictionary."""
        return {
            "id": self.id,
            "request_hash": self.request_hash,
            "candidate_name": self.candidate_name,
            "source_type": self.source_type,
            "match_score": self.match_score,
            "provider_used": self.provider_used,
            "evaluation": self.evaluation_json,
            "is_qualified": self.is_qualified,
            "match_tier": self.match_tier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<EvaluationCache(id={self.id}, candidate='{self.candidate_name}', score={self.match_score})>"


# Domain alias
CandidateEvaluation = EvaluationCache

__all__ = ["EvaluationCache", "CandidateEvaluation"]
