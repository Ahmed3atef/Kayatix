"""
Kayatix SQLAlchemy Domain Models Registry.
Clean, organized, single-file per table declarative models.
"""

from app.models.base import Base, sync_all_models_to_database, utc_now, get_current_time, get_app_timezone
from app.models.candidate import Candidate
from app.models.candidate_evaluation import CandidateEvaluation, EvaluationCache
from app.models.job import Job
from app.models.job_template import JobTemplate
from app.models.user import User
from app.models.user_settings import UserSettings

__all__ = [
    "Base",
    "get_current_time",
    "utc_now",
    "get_app_timezone",
    "sync_all_models_to_database",
    "Candidate",
    "CandidateEvaluation",
    "EvaluationCache",
    "Job",
    "JobTemplate",
    "User",
    "UserSettings",
]
