"""
User SQLAlchemy model representing system accounts and RBAC permissions.
"""

from datetime import datetime
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from app.models.base import Base, utc_now


class User(Base):
    """
    SQLAlchemy model for platform users and role-based access control (RBAC).
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="member", nullable=False, index=True)  # "admin", "recruiter", "member"
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False, index=True)
    permissions = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def __init__(self, **kwargs):
        if "is_active" not in kwargs:
            kwargs["is_active"] = True
        if "is_admin" not in kwargs:
            kwargs["is_admin"] = False
        if "role" not in kwargs:
            kwargs["role"] = "member"
        super().__init__(**kwargs)

    def set_password(self, plain_password: str, iterations: int = 100_000) -> None:
        """Cryptographically hashes and sets the user password using PBKDF2-HMAC-SHA256."""
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        self.hashed_password = f"pbkdf2:sha256:{iterations}${salt}${key.hex()}"

    def check_password(self, plain_password: str) -> bool:
        """Verifies a plain password against the stored password hash in constant time."""
        if not self.hashed_password:
            return False
        try:
            parts = self.hashed_password.split("$")
            if len(parts) != 3:
                return False
            algo_part, salt, original_hash = parts
            _, _, iterations_str = algo_part.split(":")
            iterations = int(iterations_str)

            computed = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                iterations,
            )
            return hmac.compare_digest(computed.hex(), original_hash)
        except Exception:
            return False

    def has_permission(self, action: str) -> bool:
        """Checks if the user has permission to perform a specific action."""
        if not self.is_active:
            return False
        if self.is_admin or self.role == "admin":
            return True
        if self.permissions and isinstance(self.permissions, dict):
            return bool(self.permissions.get(action, False))
        return False

    def to_dict(self, exclude_sensitive: bool = True) -> Dict[str, Any]:
        """Serializes user model to dictionary."""
        data = {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "permissions": self.permissions or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if not exclude_sensitive:
            data["hashed_password"] = self.hashed_password
        return data

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}', is_admin={self.is_admin})>"


__all__ = ["User"]
