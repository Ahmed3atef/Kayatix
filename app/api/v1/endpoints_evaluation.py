from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import HttpUrl
from app.core.database import get_db
from app.models.domain import EvaluationCache
from app.schemas.payloads import EvaluationAPIResponse, CandidateEvaluationResult
from app.services.pdf_service import extract_clean_pdf_text
from app.services.scraper_service import scrape_candidate_portfolio
from app.services.ai_engine import compute_request_hash, evaluate_candidate_with_fallback

router = APIRouter(prefix="/api/v1/evaluation", tags=["Candidate Evaluation"])


async def _process_and_cache_evaluation(
    candidate_text: str,
    job_description: str,
    source_type: str,
    db: AsyncSession,
) -> EvaluationAPIResponse:
    req_hash = compute_request_hash(candidate_text, job_description)

    # Check Database Cache First (Fast response & prevents duplicate model calls)
    stmt = select(EvaluationCache).where(EvaluationCache.request_hash == req_hash)
    result = await db.execute(stmt)
    cached_record = result.scalar_one_or_none()

    if cached_record:
        return EvaluationAPIResponse(
            cached=True,
            provider_used=cached_record.provider_used,
            analysis=CandidateEvaluationResult.model_validate(cached_record.evaluation_json),
        )

    # Run Multi-Provider AI Evaluation
    evaluation, provider = await evaluate_candidate_with_fallback(candidate_text, job_description)

    # Persist to Cache
    new_record = EvaluationCache(
        request_hash=req_hash,
        candidate_name=evaluation.candidate_name,
        source_type=source_type,
        match_score=evaluation.match_percentage,
        provider_used=provider,
        evaluation_json=evaluation.model_dump(),
    )
    db.add(new_record)
    await db.commit()

    return EvaluationAPIResponse(
        cached=False,
        provider_used=provider,
        analysis=evaluation,
    )


@router.post("/resume-pdf", response_model=EvaluationAPIResponse)
async def evaluate_pdf_resume(
    job_description: str = Form(..., description="Target Job Description text"),
    resume_file: UploadFile = File(..., description="Candidate CV or LinkedIn Export PDF"),
    db: AsyncSession = Depends(get_db),
):
    if not resume_file.filename or not resume_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted.",
        )

    try:
        pdf_bytes = await resume_file.read()
        clean_text = extract_clean_pdf_text(pdf_bytes)
        return await _process_and_cache_evaluation(clean_text, job_description, "pdf_resume", db)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.post("/portfolio-website", response_model=EvaluationAPIResponse)
async def evaluate_candidate_website(
    job_description: str = Form(..., description="Target Job Description text"),
    portfolio_url: HttpUrl = Form(..., description="Candidate personal website, blog, or GitHub URL"),
    db: AsyncSession = Depends(get_db),
):
    try:
        website_text = await scrape_candidate_portfolio(str(portfolio_url))
        return await _process_and_cache_evaluation(website_text, job_description, "portfolio_url", db)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
