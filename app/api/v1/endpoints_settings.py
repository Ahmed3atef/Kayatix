from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.payloads import (
    JobTemplateCreateRequest,
    JobTemplateResponse,
    JobTemplateUpdateRequest,
    SettingsValidationResponse,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from app.services.settings_service import (
    create_job_template,
    delete_job_template,
    get_all_job_templates,
    get_job_template_by_id,
    get_settings_summary,
    reset_default_job_templates,
    template_to_response,
    update_job_template,
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


# ==============================================================================
# Job Description Templates Endpoints
# ==============================================================================


@router.get("/templates", response_model=List[JobTemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    """Lists all configured Job Description templates."""
    templates = await get_all_job_templates(db)
    return [template_to_response(t) for t in templates]


@router.post(
    "/templates",
    response_model=JobTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: JobTemplateCreateRequest, db: AsyncSession = Depends(get_db)
):
    """Creates a new Job Description template."""
    template = await create_job_template(db, payload)
    return template_to_response(template)


@router.get("/templates/{template_id}", response_model=JobTemplateResponse)
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Retrieves a single Job Description template by ID."""
    template = await get_job_template_by_id(db, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template #{template_id} not found",
        )
    return template_to_response(template)


@router.put("/templates/{template_id}", response_model=JobTemplateResponse)
async def update_template(
    template_id: int,
    payload: JobTemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Updates an existing Job Description template."""
    updated = await update_job_template(db, template_id, payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template #{template_id} not found",
        )
    return template_to_response(updated)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Deletes a Job Description template."""
    success = await delete_job_template(db, template_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template #{template_id} not found",
        )
    return {"message": f"Template #{template_id} deleted successfully"}


@router.post("/templates/reset", response_model=List[JobTemplateResponse])
async def reset_templates(db: AsyncSession = Depends(get_db)):
    """Resets all Job Description templates to defaults."""
    templates = await reset_default_job_templates(db)
    return [template_to_response(t) for t in templates]

