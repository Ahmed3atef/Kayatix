from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON
from datetime import datetime, timezone
from app.core.database import Base


class EvaluationCache(Base):
    __tablename__ = "evaluation_cache"

    id = Column(Integer, primary_key=True, index=True)
    request_hash = Column(String(64), unique=True, index=True, nullable=False)
    candidate_name = Column(String(255), nullable=True)
    source_type = Column(String(50), nullable=False)  # "pdf_resume", "portfolio_url", "xray_snippet"
    match_score = Column(Integer, nullable=False)
    provider_used = Column(String(100), nullable=False)
    evaluation_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    required_skills = Column(JSON, nullable=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    portfolio_url = Column(String(512), nullable=True)
    linkedin_url = Column(String(512), nullable=True)
    parsed_skills = Column(JSON, nullable=True)
    years_experience = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    project_name = Column(String(255), default="AI HR Copilot & Talent Intelligence API")
    version = Column(String(50), default="1.0.0")
    gemini_api_key = Column(String(255), nullable=True)
    groq_api_key = Column(String(255), nullable=True)
    openrouter_api_key = Column(String(255), nullable=True)
    google_cse_api_key = Column(String(255), nullable=True)
    google_cse_cx_id = Column(String(255), nullable=True)
    subscription_tier = Column(String(50), default="standard")  # "standard", "pro", "enterprise"
    evaluation_mode = Column(String(50), default="hybrid")  # "hybrid", "llm_cascade", "local_offline"
    rate_limit_rpm = Column(Integer, default=15)
    env_content = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class JobTemplate(Base):
    __tablename__ = "job_templates"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(100), default="General", index=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


