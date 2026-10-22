from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models import User
from app.schemas.payloads import (
    AuthTokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
    user_to_response,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & Accounts"])


@router.post("/signup", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: UserRegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Registers a new user on the platform.
    Automatically assigns role 'member' and sets an authenticated session cookie.
    """
    user = await create_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role="member",
    )
    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})

    # Set secure HTTP-only session cookie for browser UI navigation
    response.set_cookie(
        key="kayatix_token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax",
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=user_to_response(user),
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    payload: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticates user credentials and issues an access token and session cookie.
    """
    user = await authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})

    # Set secure HTTP-only cookie
    response.set_cookie(
        key="kayatix_token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax",
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=user_to_response(user),
    )


@router.post("/logout")
async def logout(response: Response):
    """Logs out user by clearing the authenticated session cookie."""
    response.delete_cookie(key="kayatix_token")
    return {"message": "Successfully logged out."}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Returns details of the currently authenticated user."""
    return user_to_response(current_user)
