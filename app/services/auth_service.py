import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import secrets
from typing import Any, Dict, List, Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.models import User, utc_now
from app.schemas.payloads import UserResponse

logger = logging.getLogger("kayatix.auth")

DEFAULT_ADMIN_PERMISSIONS: Dict[str, bool] = {
    "can_screen": True,
    "can_source": True,
    "can_manage_users": True,
    "can_edit_settings": True,
    "can_delete_records": True,
}

DEFAULT_RECRUITER_PERMISSIONS: Dict[str, bool] = {
    "can_screen": True,
    "can_source": True,
    "can_manage_users": False,
    "can_edit_settings": False,
    "can_delete_records": False,
}

DEFAULT_MEMBER_PERMISSIONS: Dict[str, bool] = {
    "can_screen": True,
    "can_source": True,
    "can_manage_users": False,
    "can_edit_settings": False,
    "can_delete_records": False,
}


def get_default_permissions_for_role(role: str) -> Dict[str, bool]:
    """Returns default permission set based on user role."""
    r = (role or "member").lower().strip()
    if r == "admin":
        return dict(DEFAULT_ADMIN_PERMISSIONS)
    elif r == "recruiter":
        return dict(DEFAULT_RECRUITER_PERMISSIONS)
    return dict(DEFAULT_MEMBER_PERMISSIONS)


# ==============================================================================
# Password Hashing & Verification (PBKDF2-HMAC-SHA256)
# ==============================================================================

def hash_password(plain_password: str, iterations: int = 100_000) -> str:
    """Cryptographically hashes a plain text password with random salt using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"pbkdf2:sha256:{iterations}${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a stored PBKDF2-HMAC-SHA256 hash in constant time."""
    try:
        parts = hashed_password.split("$")
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
    except Exception as e:
        logger.error(f"[Auth] Error verifying password: {e}")
        return False


# ==============================================================================
# JWT / Signed Session Token Generation & Verification (HMAC-SHA256)
# ==============================================================================

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4)) if len(data) % 4 != 0 else ""
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(payload: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed HMAC-SHA256 JWT access token."""
    header = {"alg": "HS256", "typ": "JWT"}
    exp = datetime.now(timezone.utc) + (expires_delta or timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS))

    token_payload = dict(payload)
    token_payload["exp"] = int(exp.timestamp())
    token_payload["iat"] = int(datetime.now(timezone.utc).timestamp())

    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(token_payload, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a signed HMAC-SHA256 JWT token."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        provided_sig = _b64decode(sig_b64)

        if not hmac.compare_digest(expected_sig, provided_sig):
            return None

        payload_bytes = _b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Verify expiration
        exp = payload.get("exp")
        if exp and int(datetime.now(timezone.utc).timestamp()) > int(exp):
            return None

        return payload
    except Exception as e:
        logger.debug(f"[Auth] Token decoding failed: {e}")
        return None


# ==============================================================================
# User Management Operations
# ==============================================================================

def user_to_response(user: User) -> UserResponse:
    """Converts a database User model to safe API response schema."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=bool(user.is_active),
        is_admin=bool(user.is_admin),
        permissions=user.permissions or get_default_permissions_for_role(user.role),
        created_at=user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else None,
        updated_at=user.updated_at.strftime("%Y-%m-%d %H:%M") if user.updated_at else None,
    )


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Retrieves user by normalized lowercase email."""
    norm_email = email.strip().lower()
    stmt = select(User).where(User.email == norm_email)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Retrieves user by primary key ID."""
    stmt = select(User).where(User.id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_all_users(db: AsyncSession) -> List[User]:
    """Retrieves all users sorted by ID descending."""
    stmt = select(User).order_by(desc(User.id))
    return list((await db.execute(stmt)).scalars().all())


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    role: str = "member",
    is_active: bool = True,
    permissions: Optional[Dict[str, bool]] = None,
) -> User:
    """Creates a new user record with hashed password."""
    norm_email = email.strip().lower()
    existing = await get_user_by_email(db, norm_email)
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    is_admin = (role.lower().strip() == "admin")
    assigned_permissions = permissions or get_default_permissions_for_role(role)

    user = User(
        email=norm_email,
        hashed_password=hash_password(password),
        full_name=full_name.strip() if full_name else None,
        role=role.lower().strip(),
        is_active=is_active,
        is_admin=is_admin,
        permissions=assigned_permissions,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"[Auth] Created new user '{user.email}' with role '{user.role}'.")
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticates user credentials and checks active status."""
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


async def update_user_permissions(
    db: AsyncSession,
    user_id: int,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    full_name: Optional[str] = None,
    permissions: Optional[Dict[str, bool]] = None,
) -> Optional[User]:
    """Updates user role, status, name, and permissions."""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None

    if role is not None:
        user.role = role.lower().strip()
        user.is_admin = (user.role == "admin")
        if permissions is None and not user.permissions:
            user.permissions = get_default_permissions_for_role(user.role)

    if is_active is not None:
        user.is_active = is_active

    if full_name is not None:
        user.full_name = full_name.strip()

    if permissions is not None:
        # Merge or replace permissions
        current_perms = dict(user.permissions or get_default_permissions_for_role(user.role))
        current_perms.update(permissions)
        user.permissions = current_perms

    user.updated_at = utc_now()
    await db.commit()
    await db.refresh(user)
    logger.info(f"[Auth] Updated user '{user.email}' permissions (role: {user.role}, active: {user.is_active}).")
    return user


async def delete_user(db: AsyncSession, user_id: int, current_user_id: int) -> bool:
    """Deletes a user account (prevents deleting oneself)."""
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own administrator account.")

    user = await get_user_by_id(db, user_id)
    if not user:
        return False

    await db.delete(user)
    await db.commit()
    logger.info(f"[Auth] Deleted user '{user.email}' (ID: {user_id}).")
    return True


# ==============================================================================
# Default Administrator Bootstrap (via .env / system environment)
# ==============================================================================

async def bootstrap_default_admin(db: AsyncSession) -> Optional[User]:
    """
    Bootstraps the default administrator user strictly configured in .env or system environment.
    Resolution follows: .env -> system os.environ.
    If ADMIN_EMAIL and ADMIN_PASSWORD are set, guarantees the admin account exists with full rights.
    """
    admin_email = (settings.ADMIN_EMAIL or "").strip().lower()
    admin_password = (settings.ADMIN_PASSWORD or "").strip()
    admin_name = (settings.ADMIN_FULL_NAME or "Platform Administrator").strip()

    if not admin_email or not admin_password:
        logger.info("[Auth Bootstrap] No default administrator credentials provided in .env or environment.")
        return None

    user = await get_user_by_email(db, admin_email)
    if not user:
        user = User(
            email=admin_email,
            hashed_password=hash_password(admin_password),
            full_name=admin_name,
            role="admin",
            is_active=True,
            is_admin=True,
            permissions=dict(DEFAULT_ADMIN_PERMISSIONS),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"[Auth Bootstrap] Successfully initialized default administrator '{admin_email}'.")
    else:
        # Guarantee admin status and permissions
        updated = False
        if not user.is_admin or user.role != "admin":
            user.is_admin = True
            user.role = "admin"
            updated = True
        if not user.is_active:
            user.is_active = True
            updated = True
        if not user.permissions:
            user.permissions = dict(DEFAULT_ADMIN_PERMISSIONS)
            updated = True
        if updated:
            user.updated_at = utc_now()
            await db.commit()
            await db.refresh(user)
            logger.info(f"[Auth Bootstrap] Refreshed administrator privileges for '{admin_email}'.")

    return user


# ==============================================================================
# FastAPI Security & Authentication Dependencies
# ==============================================================================

def extract_token_from_request(request: Request) -> Optional[str]:
    """Extracts JWT token from Authorization header or 'kayatix_token' cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()

    cookie_token = request.cookies.get("kayatix_token")
    if cookie_token:
        return cookie_token.strip()

    return None


async def get_current_user_optional(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Retrieves current authenticated user if token is present and valid;
    returns None if anonymous (does not raise 401).
    """
    token = extract_token_from_request(request)
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        user = await get_user_by_id(db, int(user_id))
        if user and user.is_active:
            return user
    except Exception:
        pass
    return None


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    """Enforces authentication: raises 401 if user is not authenticated or inactive."""
    user = await get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Enforces administrator role: raises 403 if user is not an admin."""
    if not current_user.is_admin and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permissions required to perform this action.",
        )
    return current_user


def require_permission(permission_key: str):
    """Dependency factory checking whether user has a specific granular permission."""
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_admin:
            return current_user
        perms = current_user.permissions or {}
        if not perms.get(permission_key, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: '{permission_key}'.",
            )
        return current_user
    return permission_checker
