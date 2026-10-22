"""
Job SQLAlchemy model representing job openings and required skill criteria.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from app.models.base import Base, utc_now


class Job(Base):
    """
    SQLAlchemy model representing job openings and their criteria.
    """
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    required_skills = Column(JSON, nullable=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    @property
    def skills_list(self) -> List[str]:
        """Returns skills as a normalized list of strings."""
        if not self.required_skills:
            return []
        if isinstance(self.required_skills, list):
            return [str(s).strip() for s in self.required_skills if s]
        if isinstance(self.required_skills, str):
            try:
                parsed = json.loads(self.required_skills)
                if isinstance(parsed, list):
                    return [str(s).strip() for s in parsed if s]
            except Exception:
                return [s.strip() for s in self.required_skills.split(",") if s.strip()]
        return []

    def to_dict(self) -> Dict[str, Any]:
        """Serializes Job model to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "required_skills": self.skills_list,
            "location": self.location,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', location='{self.location}')>"


__all__ = ["Job"]
