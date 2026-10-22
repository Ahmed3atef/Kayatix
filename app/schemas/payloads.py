"""
Payload schemas re-export module.
All schemas are cleanly split into modular files:
- app.schemas.evaluation
- app.schemas.sourcing
- app.schemas.job_template
- app.schemas.settings
- app.schemas.user
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
