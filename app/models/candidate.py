"""
Candidate SQLAlchemy model representing candidate profiles and parsed resumes.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from app.models.base import Base, utc_now


class Candidate(Base):
    """
    SQLAlchemy model representing candidate profiles, skills, and portfolio links.
    """
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    portfolio_url = Column(String(512), nullable=True)
    linkedin_url = Column(String(512), nullable=True)
    parsed_skills = Column(JSON, nullable=True)
    years_experience = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    @property
    def skills_list(self) -> List[str]:
        """Returns parsed skills as a normalized list of strings."""
        if not self.parsed_skills:
            return []
        if isinstance(self.parsed_skills, list):
            return [str(s).strip() for s in self.parsed_skills if s]
        if isinstance(self.parsed_skills, str):
            try:
                parsed = json.loads(self.parsed_skills)
                if isinstance(parsed, list):
                    return [str(s).strip() for s in parsed if s]
            except Exception:
                return [s.strip() for s in self.parsed_skills.split(",") if s.strip()]
        return []

    def to_dict(self) -> Dict[str, Any]:
        """Serializes Candidate model to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "portfolio_url": self.portfolio_url,
            "linkedin_url": self.linkedin_url,
            "parsed_skills": self.skills_list,
            "years_experience": self.years_experience,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Candidate(id={self.id}, name='{self.name}', email='{self.email}')>"


__all__ = ["Candidate"]
