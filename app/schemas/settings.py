"""
Platform settings, database connection, and system defaults schemas.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.job_template import JobTemplateSchema


class UserSettingsResponse(BaseModel):
    gemini_api_key_configured: bool
    groq_api_key_configured: bool
    ollama_api_key_configured: bool
    ollama_base_url: Optional[str] = "https://ollama.com/v1"
    google_cse_cx_id_configured: bool
    subscription_tier: str = "standard"
    evaluation_mode: str = "llm_cascade"
    rate_limit_rpm: int = 15
    database_url: Optional[str] = None
    masked_database_url: Optional[str] = None
    database_type: str = "postgresql"
    env_content: Optional[str] = None
    updated_at: Optional[str] = None
    provider_health: dict[str, str] = Field(default_factory=dict)


class UserSettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    ollama_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    google_cse_cx_id: Optional[str] = None
    subscription_tier: Optional[str] = None
    evaluation_mode: Optional[str] = None
    rate_limit_rpm: Optional[int] = None
    database_url: Optional[str] = None
    env_content: Optional[str] = None


class DatabaseValidationRequest(BaseModel):
    database_url: Optional[str] = None


class DatabaseValidationResponse(BaseModel):
    status: str  # "valid", "invalid"
    message: str
    database_type: str  # "sqlite", "postgresql"
    normalized_url: Optional[str] = None
    latency_ms: Optional[float] = None
    tables_found: List[str] = []


class ProviderValidationStatus(BaseModel):
    status: str  # "valid", "invalid", "unconfigured"
    message: str
    model_tested: Optional[str] = None


class SettingsValidationResponse(BaseModel):
    gemini: ProviderValidationStatus
    groq: ProviderValidationStatus
    ollama: ProviderValidationStatus
    google_cse: ProviderValidationStatus
    overall_ready: bool


class SystemSettingsDefaultsSchema(BaseModel):
    project_name: str = Field(default="Kayatix - A.Y.A.T. Engine", description="Default project or platform name")
    version: str = Field(default="1.0.0", description="Default application version")
    subscription_tier: str = Field(default="standard", description="Default subscription tier")
    evaluation_mode: str = Field(default="llm_cascade", description="Default candidate evaluation mode")
    rate_limit_rpm: int = Field(default=15, ge=1, le=1000, description="Default rate limit in requests per minute")


class AppDefaultsSchema(BaseModel):
    version: str = Field(default="1.0.0", description="Schema specification version")
    modified_timestamp: Optional[str] = Field(
        default="2026-10-16T19:00:00Z",
        description="ISO timestamp marking when the schema file was last modified"
    )
    system_settings: SystemSettingsDefaultsSchema = Field(
        default_factory=SystemSettingsDefaultsSchema,
        description="System configuration defaults"
    )
    job_templates: List[JobTemplateSchema] = Field(
        default_factory=list,
        description="List of standard job description templates"
    )


class DefaultsSyncResult(BaseModel):
    templates_inserted: int = Field(default=0, description="Number of new templates inserted into database")
    templates_updated: int = Field(default=0, description="Number of existing templates updated with modified schema data")
    templates_unchanged: int = Field(default=0, description="Number of templates already in sync")
    settings_synced: bool = Field(default=False, description="Whether system settings defaults were updated in database")
    instructions_synced: bool = Field(default=False, description="Deprecated / Kept for backwards compatibility")
    message: str = Field(default="", description="Human-readable synchronization summary message")


class DefaultsSchemaResponse(BaseModel):
    json_schema: Dict[str, Any] = Field(description="Frappe DocType JSON Schema specification")
    defaults: AppDefaultsSchema = Field(description="Active default data payload")


class FrappeDocTypeResponse(BaseModel):
    name: str = Field(description="DocType name")
    doctype: str = Field(default="DocType", description="Frappe DocType indicator")
    module: str = Field(default="Kayatix", description="Frappe module")
    schema_data: Dict[str, Any] = Field(description="Full Frappe DocType JSON schema definition")


__all__ = [
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
]
