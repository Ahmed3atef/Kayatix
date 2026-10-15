from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.payloads import (
    SettingsValidationResponse,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from app.services.settings_service import (
    get_settings_summary,
    update_user_settings,
    validate_all_settings,
)

router = APIRouter(prefix="/api/v1/settings", tags=["User Settings & Accounts"])


@router.get("", response_model=UserSettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Retrieves safe configuration overview and subscription status."""
    return await get_settings_summary(db)


@router.put("", response_model=UserSettingsResponse)
async def update_settings(
    payload: UserSettingsUpdateRequest, db: AsyncSession = Depends(get_db)
):
    """Updates API provider credentials and subscription tier."""
    return await update_user_settings(payload, db)


@router.post("/validate", response_model=SettingsValidationResponse)
async def validate_credentials(
    payload: UserSettingsUpdateRequest = None, db: AsyncSession = Depends(get_db)
):
    """Validates connectivity to all configured AI providers and Google CSE."""
    return await validate_all_settings(payload, db)
