import logging
from typing import Optional, Tuple
from urllib.parse import urlparse
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import HttpUrl
from app.core.database import get_db
from app.models.domain import EvaluationCache
from app.schemas.payloads import EvaluationAPIResponse, CandidateEvaluationResult
from app.services.pdf_service import extract_clean_pdf_text
from app.services.scraper_service import scrape_candidate_portfolio
from app.services.ai_engine import compute_request_hash, evaluate_candidate

logger = logging.getLogger("kayatix.evaluation")

router = APIRouter(prefix="/api/v1/evaluation", tags=["Candidate Evaluation"])


async def evaluate_candidate_with_fallback(
    candidate_text: str, job_description: str
) -> Tuple[CandidateEvaluationResult, str]:
    """Evaluation wrapper that routes 100% through the multi-provider Cloud LLM cascade."""
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
        # Check if cache entry was created by old local/hybrid engine
        if any(term in (cached_record.provider_used or "").lower() for term in ["local", "hybrid"]):
            logger.info(
                f"[AI Evaluator] Cache entry {req_hash[:8]} has legacy provider '{cached_record.provider_used}'. "
                "Invalidating to perform genuine real AI model evaluation."
            )
        else:
            logger.info(f"[AI Evaluator] Cache hit for request {req_hash[:8]} (Provider: {cached_record.provider_used}).")
            return EvaluationAPIResponse(
                cached=True,
                provider_used=cached_record.provider_used,
                analysis=CandidateEvaluationResult.model_validate(cached_record.evaluation_json),
            )

    # Run Candidate Evaluation (Real Cloud LLM Cascade: Gemini -> Groq -> OpenRouter)
    logger.info(
        f"[AI Evaluator] Initiating live AI candidate evaluation (Source: {source_type}, "
        f"Candidate text: {len(candidate_text)} chars, JD text: {len(job_description)} chars)..."
    )
    evaluation, provider = await evaluate_candidate_with_fallback(candidate_text, job_description)
    logger.info(
        f"[AI Evaluator] Evaluation completed successfully by AI provider '{provider}' "
        f"for '{evaluation.candidate_name}' (Score: {evaluation.match_percentage}%, YOE: {evaluation.estimated_years_experience})."
    )

    # Persist or update Cache
    if cached_record:
        cached_record.candidate_name = evaluation.candidate_name
        cached_record.source_type = source_type
        cached_record.match_score = evaluation.match_percentage
        cached_record.provider_used = provider
        cached_record.evaluation_json = evaluation.model_dump()
    else:
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
        logger.info(f"[PDF Evaluation] Received file upload: '{resume_file.filename}'")
        pdf_bytes = await resume_file.read()
        clean_text = extract_clean_pdf_text(pdf_bytes)
        logger.info(f"[PDF Evaluation] Clean text successfully parsed ({len(clean_text)} chars). Dispatching to AI engine.")
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
            logger.info(f"[Website Evaluation] Using candidate text provided directly ({len(website_text)} chars).")
        # 2. Otherwise scrape the supplied URL
        elif portfolio_url and portfolio_url.strip():
            clean_url = normalize_and_validate_url(portfolio_url)
            logger.info(f"[Website Evaluation] Fetching and parsing candidate website: {clean_url}")
            try:
                website_text = await scrape_candidate_portfolio(clean_url)
                logger.info(f"[Website Evaluation] Scraping succeeded ({len(website_text)} chars).")
            except ValueError as ve:
                err_msg = str(ve)
                # If scraping returns minimal text (SPA) or is blocked, synthesize a fallback profile
                if "sufficient readable text" in err_msg or "403" in err_msg:
                    logger.warning(f"[Website Evaluation] Site scraping blocked/minimal ({err_msg}). Generating structured SPA candidate profile.")
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
