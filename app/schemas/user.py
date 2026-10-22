"""
User management and authentication schemas.
"""

from typing import Dict, Optional
from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="Valid user email address")
    password: str = Field(..., min_length=6, description="User password (min 6 chars)")
    full_name: Optional[str] = Field(None, max_length=255, description="Full name")


class UserLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="Registered user email address")
    password: str = Field(..., description="User password")


class UserCreateRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    password: str = Field(..., min_length=6, description="User password (min 6 chars)")
    full_name: Optional[str] = Field(None, max_length=255, description="Full name")
    role: str = Field(default="member", description="Role: admin, recruiter, or member")
    is_active: bool = Field(default=True, description="Active status")
    permissions: Optional[Dict[str, bool]] = Field(default=None, description="Granular permission flags")


class UserPermissionsUpdateRequest(BaseModel):
    role: Optional[str] = Field(None, description="Role: admin, recruiter, or member")
    is_active: Optional[bool] = Field(None, description="Active status")
    full_name: Optional[str] = Field(None, description="Updated full name")
    permissions: Optional[Dict[str, bool]] = Field(None, description="Granular permission flags")


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    is_admin: bool
    permissions: Optional[Dict[str, bool]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


__all__ = [
    "UserRegisterRequest",
    "UserLoginRequest",
    "UserCreateRequest",
    "UserPermissionsUpdateRequest",
    "UserResponse",
    "AuthTokenResponse",
]
