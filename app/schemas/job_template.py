"""
Job Template request, response, and schema definitions.
"""

from typing import Optional
from pydantic import BaseModel, Field


class JobTemplateCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    category: str = Field(default="General", max_length=100)
    description: str = Field(..., min_length=10)


class JobTemplateUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, min_length=10)


class JobTemplateResponse(BaseModel):
    id: int
    title: str
    category: str
    description: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobTemplateSchema(BaseModel):
    title: str = Field(..., min_length=2, max_length=255, description="Official job title")
    category: str = Field(default="General", max_length=100, description="Department or job category")
    description: str = Field(..., min_length=10, description="Full job description requirements and specs")


__all__ = [
    "JobTemplateCreateRequest",
    "JobTemplateUpdateRequest",
    "JobTemplateResponse",
    "JobTemplateSchema",
]
