from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models import User
from app.schemas.payloads import (
    UserCreateRequest,
    UserPermissionsUpdateRequest,
    UserResponse,
)
from app.services.auth_service import (
    create_user,
    delete_user,
    get_all_users,
    get_user_by_id,
    require_admin,
    update_user_permissions,
    user_to_response,
)

router = APIRouter(prefix="/api/v1/users", tags=["User Management (Admin Only)"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Lists all users on the platform. Restricted to administrators."""
    users = await get_all_users(db)
    return [user_to_response(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_by_admin(
    payload: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Creates a new user with specific role and permissions. Restricted to administrators."""
    user = await create_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        permissions=payload.permissions,
    )
    return user_to_response(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Retrieves user profile by ID. Restricted to administrators."""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user_to_response(user)


@router.put("/{user_id}/permissions", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserPermissionsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Updates a user's role (admin, recruiter, member), active status, or granular permissions.
    Restricted to administrators.
    """
    user = await update_user_permissions(
        db=db,
        user_id=user_id,
        role=payload.role,
        is_active=payload.is_active,
        full_name=payload.full_name,
        permissions=payload.permissions,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user_to_response(user)


@router.delete("/{user_id}")
async def remove_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Deletes a user account.
    Restricted to administrators. Prevents deleting oneself.
    """
    success = await delete_user(db, user_id=user_id, current_user_id=admin.id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"message": f"User {user_id} deleted successfully."}
