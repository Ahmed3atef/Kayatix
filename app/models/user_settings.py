"""
UserSettings SQLAlchemy model representing global platform settings and API credentials.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse
from sqlalchemy import Column, DateTime, Integer, String, Text
from app.models.base import Base, utc_now


class UserSettings(Base):
    """
    SQLAlchemy model representing system configuration, LLM API keys, and database URLs.
    """
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    project_name = Column(String(255), default="AI HR Copilot & Talent Intelligence API")
    version = Column(String(50), default="1.0.0")
    gemini_api_key = Column(String(255), nullable=True)
    groq_api_key = Column(String(255), nullable=True)
    ollama_api_key = Column(String(255), nullable=True)
    ollama_base_url = Column(String(255), default="https://ollama.com/v1", nullable=True)
    google_cse_cx_id = Column(String(255), nullable=True)
    subscription_tier = Column(String(50), default="standard")  # "standard", "pro", "enterprise"
    evaluation_mode = Column(String(50), default="llm_cascade")
    rate_limit_rpm = Column(Integer, default=15)
    database_url = Column(String(1024), nullable=True)
    env_content = Column(Text, nullable=True)
    job_templates_schema_timestamp = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    @property
    def database_type(self) -> str:
        """Identifies whether configured database is PostgreSQL or SQLite."""
        if self.database_url and ("postgres" in self.database_url.lower()):
            return "postgresql"
        return "sqlite"

    @property
    def masked_database_url(self) -> str:
        """Returns database connection string with password safely masked."""
        if not self.database_url or not self.database_url.strip():
            return "Not Configured"
        try:
            parsed = urlparse(self.database_url.strip())
            if parsed.password:
                netloc = parsed.netloc.replace(f":{parsed.password}@", ":••••••••@")
                return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        except Exception:
            pass
        return self.database_url.strip()

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        """Serializes settings to a dictionary, optionally masking credentials."""
        def mask(val: Optional[str]) -> Optional[str]:
            if not val or not mask_secrets:
                return val
            if len(val) <= 8:
                return "••••••••"
            return val[:4] + "••••" + val[-4:]

        return {
            "id": self.id,
            "project_name": self.project_name,
            "version": self.version,
            "gemini_api_key": mask(self.gemini_api_key),
            "groq_api_key": mask(self.groq_api_key),
            "ollama_api_key": mask(self.ollama_api_key),
            "ollama_base_url": self.ollama_base_url,
            "google_cse_cx_id": mask(self.google_cse_cx_id),
            "subscription_tier": self.subscription_tier,
            "evaluation_mode": self.evaluation_mode,
            "rate_limit_rpm": self.rate_limit_rpm,
            "database_url": self.masked_database_url if mask_secrets else self.database_url,
            "database_type": self.database_type,
            "job_templates_schema_timestamp": self.job_templates_schema_timestamp,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<UserSettings(id={self.id}, project='{self.project_name}', db_type='{self.database_type}')>"


__all__ = ["UserSettings"]
