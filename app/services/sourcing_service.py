import logging
from typing import List
import httpx
from app.core.config import settings
from app.schemas.payloads import XRaySearchRequest, XRayProfileItem

logger = logging.getLogger("kayatix.sourcing")


async def execute_linkedin_xray_search(req: XRaySearchRequest) -> List[XRayProfileItem]:
    """
    Uses Google Custom Search JSON API to perform legal X-Ray searches
    over publicly indexed LinkedIn profiles without touching LinkedIn servers directly.
    """
    api_key = settings.GOOGLE_CSE_API_KEY
    cx_id = settings.GOOGLE_CSE_CX_ID

    if not api_key or not cx_id:
        try:
            from sqlalchemy import select
            from app.core.database import AsyncSessionLocal
            from app.models.domain import UserSettings

            async with AsyncSessionLocal() as session:
                stmt = select(UserSettings)
                db_settings = (await session.execute(stmt)).scalars().first()
                if db_settings:
                    api_key = api_key or db_settings.google_cse_api_key
                    cx_id = cx_id or db_settings.google_cse_cx_id
                    if db_settings.google_cse_api_key:
                        settings.GOOGLE_CSE_API_KEY = db_settings.google_cse_api_key
                    if db_settings.google_cse_cx_id:
                        settings.GOOGLE_CSE_CX_ID = db_settings.google_cse_cx_id
        except Exception:
            pass

    if not api_key or not cx_id:
        logger.warning("[X-Ray Sourcing] Google Custom Search credentials missing.")
        raise ValueError(
            "Google Custom Search API credentials are not configured in Settings / .env. "
            "(Tip: You can use the 1-Click Search on Google button or the CSE Widget without an API key!)"
        )

    skills_query = " AND ".join([f'"{skill}"' for skill in req.required_skills[:4]])
    dork_query = f'site:linkedin.com/in/ "{req.job_title}" AND "{req.location}" AND {skills_query}'
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx_id,
        "q": dork_query,
        "num": req.max_results,
    }

    logger.info(f"[X-Ray Sourcing] Executing Google CSE search: '{dork_query[:90]}...' (Max results: {req.max_results})")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            err_text = resp.text
            logger.error(f"[X-Ray Sourcing] Google Search API error (HTTP {resp.status_code}): {err_text}")
            if "API_KEY_SERVICE_BLOCKED" in err_text or "PERMISSION_DENIED" in err_text:
                logger.warning(
                    "[X-Ray Sourcing] Note: Your GCP API key has restrictions blocking 'customsearch.googleapis.com'. "
                    "Enable 'Custom Search API' in Google Cloud Console or use the 1-Click Direct Google Search button."
                )
                raise RuntimeError(
                    f"Google Search API error: Requests to Custom Search are blocked (API_KEY_SERVICE_BLOCKED). "
                    "Please enable the 'Custom Search API' in your Google Cloud Console for project restrictions, "
                    "or click the '1-Click Direct Google Search' button on this page to search instantly without an API key."
                )
            raise RuntimeError(f"Google Search API error: {err_text}")
        data = resp.json()

    results: List[XRayProfileItem] = []
    for item in data.get("items", []):
        results.append(
            XRayProfileItem(
                full_title=item.get("title", ""),
                linkedin_url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
        )
    logger.info(f"[X-Ray Sourcing] Successfully retrieved {len(results)} candidate profile(s).")
    return results
