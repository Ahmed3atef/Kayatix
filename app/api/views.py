import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.domain import EvaluationCache
from app.services.settings_service import (
    get_all_job_templates,
    get_or_create_user_settings,
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
from app.core.config import settings
from app.services.settings_service import provider_health_cache
templates.env.globals["app_settings"] = settings
templates.env.globals["provider_health"] = provider_health_cache

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def dashboard_view(request: Request, db: AsyncSession = Depends(get_db)):
    """Main Dashboard: system overview, real-time HR talent metrics, and recent activities."""
    stmt = select(EvaluationCache).order_by(desc(EvaluationCache.id)).limit(8)
    recent_evaluations = (await db.execute(stmt)).scalars().all()

    # 1. Total Screened Candidates
    total_stmt = select(func.count(EvaluationCache.id))
    total_evals = (await db.execute(total_stmt)).scalar() or 0

    # 2. Average Benchmark Match Score
    avg_stmt = select(func.avg(EvaluationCache.match_score))
    avg_score_raw = (await db.execute(avg_stmt)).scalar()
    avg_match_score = round(float(avg_score_raw), 1) if avg_score_raw is not None else 0.0

    # 3. Qualified Shortlist (Score >= 75)
    qualified_stmt = select(func.count(EvaluationCache.id)).where(EvaluationCache.match_score >= 75)
    qualified_count = (await db.execute(qualified_stmt)).scalar() or 0
    qualification_rate = round((qualified_count / total_evals) * 100) if total_evals > 0 else 0

    # 4. Average Years of Experience (YOE)
    all_json_stmt = select(EvaluationCache.evaluation_json)
    all_jsons = (await db.execute(all_json_stmt)).scalars().all()
    yoe_list = [
        ev.get("estimated_years_experience")
        for ev in all_jsons
        if isinstance(ev, dict) and ev.get("estimated_years_experience") is not None
    ]
    avg_yoe = round(sum(yoe_list) / len(yoe_list), 1) if yoe_list else 0.0

    # 5. Fit Breakdown for HR distribution
    mod_fit_stmt = select(func.count(EvaluationCache.id)).where(
        EvaluationCache.match_score >= 50, EvaluationCache.match_score < 75
    )
    moderate_fit_count = (await db.execute(mod_fit_stmt)).scalar() or 0

    low_fit_stmt = select(func.count(EvaluationCache.id)).where(EvaluationCache.match_score < 50)
    low_fit_count = (await db.execute(low_fit_stmt)).scalar() or 0

    user_settings = await get_or_create_user_settings(db)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "recent_evaluations": recent_evaluations,
            "total_evaluations": total_evals,
            "avg_match_score": avg_match_score,
            "qualified_count": qualified_count,
            "qualification_rate": qualification_rate,
            "avg_yoe": avg_yoe,
            "high_fit_count": qualified_count,
            "moderate_fit_count": moderate_fit_count,
            "low_fit_count": low_fit_count,
            "subscription_tier": user_settings.subscription_tier or "standard",
        },
    )


@router.get("/screener", response_class=HTMLResponse)
async def screener_view(request: Request, db: AsyncSession = Depends(get_db)):
    """Dedicated Resume Screener: Ingest PDF resumes & evaluate against Job Descriptions."""
    user_settings = await get_or_create_user_settings(db)
    job_templates = await get_all_job_templates(db)
    templates_payload = [
        {"id": t.id, "title": t.title, "category": t.category, "description": t.description}
        for t in job_templates
    ]
    return templates.TemplateResponse(
        request=request,
        name="screener.html",
        context={
            "settings": user_settings,
            "job_templates": job_templates,
            "job_templates_json": json.dumps(templates_payload),
        },
    )


@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_view(request: Request, db: AsyncSession = Depends(get_db)):
    """Dedicated Portfolio Analyzer: Scrapes & analyzes candidate blogs and GitHub profiles."""
    user_settings = await get_or_create_user_settings(db)
    job_templates = await get_all_job_templates(db)
    templates_payload = [
        {"id": t.id, "title": t.title, "category": t.category, "description": t.description}
        for t in job_templates
    ]
    return templates.TemplateResponse(
        request=request,
        name="portfolio.html",
        context={
            "settings": user_settings,
            "job_templates": job_templates,
            "job_templates_json": json.dumps(templates_payload),
        },
    )


@router.get("/sourcing", response_class=HTMLResponse)
async def sourcing_view(request: Request, db: AsyncSession = Depends(get_db)):
    """Dedicated Legal LinkedIn Sourcing: Google X-Ray Dorking engine."""
    user_settings = await get_or_create_user_settings(db)
    return templates.TemplateResponse(
        request=request,
        name="sourcing.html",
        context={
            "settings": user_settings,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def history_view(
    request: Request,
    q: Optional[str] = Query(None, description="Search candidate name or keyword"),
    source: Optional[str] = Query(None, description="Filter by source type"),
    db: AsyncSession = Depends(get_db),
):
    """Dedicated Evaluation History & Cache Explorer: View all deduplicated evaluations."""
    stmt = select(EvaluationCache).order_by(desc(EvaluationCache.id))

    if q:
        stmt = stmt.where(EvaluationCache.candidate_name.ilike(f"%{q}%"))
    if source:
        stmt = stmt.where(EvaluationCache.source_type == source)

    records = (await db.execute(stmt)).scalars().all()
    total_count = len(records)

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "records": records,
            "total_count": total_count,
            "query": q or "",
            "source_filter": source or "",
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request, db: AsyncSession = Depends(get_db)):
    """Dedicated Settings Page: Manage AI provider accounts, subscriptions, and diagnostics."""
    user_settings = await get_or_create_user_settings(db)
    job_templates = await get_all_job_templates(db)
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings": user_settings,
            "job_templates": job_templates,
        },
    )


@router.get("/evaluations/{evaluation_id}", response_class=HTMLResponse)
async def evaluation_detail_view(
    evaluation_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Detailed candidate assessment report with score breakdown and interview questions."""
    stmt = select(EvaluationCache).where(EvaluationCache.id == evaluation_id)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Evaluation record not found")

    return templates.TemplateResponse(
        request=request,
        name="evaluation_detail.html",
        context={
            "record": record,
        },
    )


from app.services.docs_service import get_documentation_page

@router.get("/documentation", response_class=HTMLResponse)
@router.get("/documentation/{doc_slug}", response_class=HTMLResponse)
async def documentation_view(
    request: Request,
    doc_slug: Optional[str] = None,
):
    """Interactive Knowledge Base & Documentation: Dynamically loads and renders local Markdown pages."""
    doc_data = get_documentation_page(doc_slug)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Documentation page not found")

    return templates.TemplateResponse(
        request=request,
        name="documentation.html",
        context={
            "doc": doc_data,
        },
    )

