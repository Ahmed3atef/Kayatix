"""
Pydantic API schemas for request validation and response serialization.
Modularized by functional domain.
"""

from app.schemas.evaluation import (
    CandidateEvaluationResult,
    EvaluationAPIResponse,
    InterviewQuestionSchema,
)
from app.schemas.job_template import (
    JobTemplateCreateRequest,
    JobTemplateResponse,
    JobTemplateSchema,
    JobTemplateUpdateRequest,
)
from app.schemas.settings import (
    AppDefaultsSchema,
    DatabaseValidationRequest,
    DatabaseValidationResponse,
    DefaultsSchemaResponse,
    DefaultsSyncResult,
    FrappeDocTypeResponse,
    ProviderValidationStatus,
    SettingsValidationResponse,
    SystemSettingsDefaultsSchema,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from app.schemas.sourcing import (
    XRayProfileItem,
    XRaySearchRequest,
)
from app.schemas.user import (
    AuthTokenResponse,
    UserCreateRequest,
    UserLoginRequest,
    UserPermissionsUpdateRequest,
    UserRegisterRequest,
    UserResponse,
)

__all__ = [
    # Evaluation
    "InterviewQuestionSchema",
    "CandidateEvaluationResult",
    "EvaluationAPIResponse",
    # Sourcing
    "XRaySearchRequest",
    "XRayProfileItem",
    # Job Templates
    "JobTemplateCreateRequest",
    "JobTemplateUpdateRequest",
    "JobTemplateResponse",
    "JobTemplateSchema",
    # Settings
    "UserSettingsResponse",
    "UserSettingsUpdateRequest",
    "DatabaseValidationRequest",
    "DatabaseValidationResponse",
    "ProviderValidationStatus",
    "SettingsValidationResponse",
    "SystemSettingsDefaultsSchema",
    "AppDefaultsSchema",
    "DefaultsSyncResult",
    "DefaultsSchemaResponse",
    "FrappeDocTypeResponse",
    # Users & Auth
    "UserRegisterRequest",
    "UserLoginRequest",
    "UserCreateRequest",
    "UserPermissionsUpdateRequest",
    "UserResponse",
    "AuthTokenResponse",
]
