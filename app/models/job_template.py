"""
JobTemplate SQLAlchemy model representing reusable benchmark job descriptions.
"""

from datetime import datetime
from typing import Any, Dict
from sqlalchemy import Column, DateTime, Integer, String, Text
from app.models.base import Base, utc_now


class JobTemplate(Base):
    """
    SQLAlchemy model representing reusable job description templates.
    """
    __tablename__ = "job_templates"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(100), default="General", index=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes JobTemplate to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_response(self) -> Dict[str, Any]:
        """Schema-compatible response dictionary."""
        return self.to_dict()

    def __repr__(self) -> str:
        return f"<JobTemplate(id={self.id}, title='{self.title}', category='{self.category}')>"


__all__ = ["JobTemplate"]
