from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import HttpUrl
from app.core.database import get_db
from app.models.domain import EvaluationCache
from app.schemas.payloads import EvaluationAPIResponse, CandidateEvaluationResult
from app.services.pdf_service import extract_clean_pdf_text
from app.services.scraper_service import scrape_candidate_portfolio
from typing import Tuple
from app.services.ai_engine import compute_request_hash, evaluate_candidate

router = APIRouter(prefix="/api/v1/evaluation", tags=["Candidate Evaluation"])


async def evaluate_candidate_with_fallback(
    candidate_text: str, job_description: str
) -> Tuple[CandidateEvaluationResult, str]:
    """Evaluation wrapper that routes through the active EVALUATION_MODE (hybrid/local/cascade)."""
    return await evaluate_candidate(candidate_text, job_description)


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

    # Run Candidate Evaluation (Hybrid / Local / LLM Cascade according to Settings)
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


from urllib.parse import urlparse

def normalize_and_validate_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("Portfolio URL cannot be empty.")
    if not url.startswith(("http://", "https://")):
        if "." not in url or " " in url or url.startswith("/"):
            raise ValueError("Invalid URL format. Please provide a valid URL (e.g. https://github.com/username)")
        url = f"https://{url}"

    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc or parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid URL format. Please provide a valid URL (e.g. https://github.com/username)")
    return url


from typing import Optional

@router.post("/portfolio-website", response_model=EvaluationAPIResponse)
async def evaluate_candidate_website(
    job_description: str = Form(..., description="Target Job Description text"),
    portfolio_url: Optional[str] = Form(None, description="Candidate personal website, blog, or GitHub URL"),
    portfolio_text: Optional[str] = Form(None, description="Directly pasted portfolio bio or text (optional fallback for SPAs)"),
    db: AsyncSession = Depends(get_db),
):
    try:
        # 1. If direct portfolio text was supplied, use it
        if portfolio_text and len(portfolio_text.strip()) >= 15:
            website_text = portfolio_text.strip()
        # 2. Otherwise scrape the supplied URL
        elif portfolio_url and portfolio_url.strip():
            clean_url = normalize_and_validate_url(portfolio_url)
            try:
                website_text = await scrape_candidate_portfolio(clean_url)
            except ValueError as ve:
                err_msg = str(ve)
                # If scraping returns minimal text (SPA) or is blocked, synthesize a fallback profile
                if "sufficient readable text" in err_msg or "403" in err_msg:
                    parsed_u = urlparse(clean_url)
                    host = parsed_u.netloc or clean_url
                    path_slug = parsed_u.path.strip("/").replace("-", " ").title()
                    candidate_hint = path_slug if path_slug else host.split(".")[0].replace("-", " ").title()
                    website_text = (
                        f"Candidate Web Portfolio: {clean_url}\n"
                        f"Candidate Name/Identifier: {candidate_hint}\n"
                        f"Host Domain: {host}\n"
                        f"Website Architecture: Client-Side JavaScript Single-Page Application (SPA)\n"
                        f"Evaluation Summary: Evaluated based on available web indicators and candidate identifiers."
                    )
                else:
                    raise ve
        else:
            raise ValueError("Please provide a candidate Portfolio URL or paste portfolio text directly.")

        return await _process_and_cache_evaluation(website_text, job_description, "portfolio_site", db)
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
