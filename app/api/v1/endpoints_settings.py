from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.payloads import (
    AppDefaultsSchema,
    DatabaseValidationRequest,
    DatabaseValidationResponse,
    DefaultsSchemaResponse,
    DefaultsSyncResult,
    JobTemplateCreateRequest,
    JobTemplateResponse,
    JobTemplateUpdateRequest,
    RAGAIInstructionResponse,
    RAGAIInstructionSchema,
    SettingsValidationResponse,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from app.services.settings_service import (
    create_job_template,
    delete_job_template,
    get_all_job_templates,
    get_defaults_json_schema,
    get_job_template_by_id,
    get_rag_ai_instructions_json_schema,
    get_settings_summary,
    load_default_settings_schema,
    load_rag_ai_instructions_schema,
    reset_default_job_templates,
    save_default_settings_schema,
    save_rag_ai_instructions_schema,
    sync_ai_instruction_to_json_file,
    sync_ai_instructions_to_database,
    sync_global_defaults,
    sync_job_templates_to_json_file,
    template_to_response,
    update_job_template,
    update_user_settings,
    validate_all_settings,
    validate_database_connection,
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


@router.post("/validate-database", response_model=DatabaseValidationResponse)
async def validate_database_endpoint(payload: DatabaseValidationRequest):
    """Validates connectivity to a PostgreSQL or SQLite database link."""
    return await validate_database_connection(payload.database_url)


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


# ==============================================================================
# Global JSON Settings Schema & Database Synchronization Endpoints
# ==============================================================================

@router.get("/schema/defaults", response_model=DefaultsSchemaResponse)
async def get_defaults_schema():
    """
    Returns the official JSON Settings Schema and current active default data
    (including DEFAULT_JOB_TEMPLATES and system configuration defaults).
    """
    return DefaultsSchemaResponse(
        json_schema=get_defaults_json_schema(),
        defaults=load_default_settings_schema(),
    )


@router.post("/schema/defaults/sync", response_model=DefaultsSyncResult)
async def sync_defaults_into_database(
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Performs global insertion and synchronization of the JSON settings schema into the active database.
    - If defaults are missing, inserts them.
    - If modified schema data changed (e.g. template description or category), syncs updates to existing records.
    - Preserves user custom templates and user credentials.
    """
    return await sync_global_defaults(db, force=force)


@router.put("/schema/defaults", response_model=DefaultsSyncResult)
async def update_defaults_schema_and_sync(
    payload: AppDefaultsSchema,
    db: AsyncSession = Depends(get_db),
):
    """
    Validates and updates the JSON defaults schema configuration file on disk,
    then automatically runs a global synchronization into the active database.
    """
    save_default_settings_schema(payload)
    return await sync_global_defaults(db, force=True)


@router.post("/schema/templates/export", response_model=AppDefaultsSchema)
async def export_database_templates_to_json(db: AsyncSession = Depends(get_db)):
    """
    Reverse sync: Exports current database JobTemplates and UserSettings to default_job_templates.json
    with an updated modified_timestamp.
    """
    return await sync_job_templates_to_json_file(db)


# ==============================================================================
# RAG Prompt Template & AI System Instructions Endpoints
# ==============================================================================

@router.get("/schema/ai-instructions", response_model=RAGAIInstructionResponse)
async def get_ai_instructions(db: AsyncSession = Depends(get_db)):
    """
    Retrieves the active RAG prompt template and AI system instruction from the database.
    Includes the official JSON Schema definition for validation.
    """
    from sqlalchemy import select
    from app.models.domain import AIInstruction
    stmt = select(AIInstruction).where(AIInstruction.name == "default_evaluator")
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()

    if not inst:
        inst = await sync_ai_instructions_to_database(db)

    return RAGAIInstructionResponse(
        id=inst.id,
        name=inst.name,
        description=inst.description,
        modified_timestamp=inst.modified_timestamp,
        system_instruction=inst.system_instruction,
        rag_prompt_template=inst.rag_prompt_template,
        created_at=inst.created_at.strftime("%Y-%m-%d %H:%M") if inst.created_at else None,
        updated_at=inst.updated_at.strftime("%Y-%m-%d %H:%M") if inst.updated_at else None,
        json_schema=get_rag_ai_instructions_json_schema(),
    )


@router.post("/schema/ai-instructions/sync", response_model=RAGAIInstructionResponse)
async def sync_ai_instructions(
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronizes RAG & AI instructions from rag_ai_instructions.json into the active database.
    Checks modified_timestamp to detect if file changed.
    """
    inst = await sync_ai_instructions_to_database(db, force=force)
    return RAGAIInstructionResponse(
        id=inst.id,
        name=inst.name,
        description=inst.description,
        modified_timestamp=inst.modified_timestamp,
        system_instruction=inst.system_instruction,
        rag_prompt_template=inst.rag_prompt_template,
        created_at=inst.created_at.strftime("%Y-%m-%d %H:%M") if inst.created_at else None,
        updated_at=inst.updated_at.strftime("%Y-%m-%d %H:%M") if inst.updated_at else None,
        json_schema=get_rag_ai_instructions_json_schema(),
    )


@router.put("/schema/ai-instructions", response_model=RAGAIInstructionResponse)
async def update_ai_instructions(
    payload: RAGAIInstructionSchema,
    db: AsyncSession = Depends(get_db),
):
    """
    Updates RAG & AI instructions in both rag_ai_instructions.json and the database.
    Updates modified_timestamp to ensure both stay strictly in sync.
    """
    save_rag_ai_instructions_schema(payload)
    inst = await sync_ai_instructions_to_database(db, force=True)
    return RAGAIInstructionResponse(
        id=inst.id,
        name=inst.name,
        description=inst.description,
        modified_timestamp=inst.modified_timestamp,
        system_instruction=inst.system_instruction,
        rag_prompt_template=inst.rag_prompt_template,
        created_at=inst.created_at.strftime("%Y-%m-%d %H:%M") if inst.created_at else None,
        updated_at=inst.updated_at.strftime("%Y-%m-%d %H:%M") if inst.updated_at else None,
        json_schema=get_rag_ai_instructions_json_schema(),
    )


@router.post("/schema/ai-instructions/export", response_model=RAGAIInstructionSchema)
async def export_ai_instructions_to_json(db: AsyncSession = Depends(get_db)):
    """
    Reverse sync: Reads AIInstruction from the database, updates modified_timestamp,
    and updates rag_ai_instructions.json.
    """
    return await sync_ai_instruction_to_json_file(db)



