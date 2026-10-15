from typing import List
import httpx
from app.core.config import settings
from app.schemas.payloads import XRaySearchRequest, XRayProfileItem


async def execute_linkedin_xray_search(req: XRaySearchRequest) -> List[XRayProfileItem]:
    """
    Uses Google Custom Search JSON API to perform legal X-Ray searches
    over publicly indexed LinkedIn profiles without touching LinkedIn servers directly.
    """
    if not settings.GOOGLE_CSE_API_KEY or not settings.GOOGLE_CSE_CX_ID:
        raise ValueError("Google Custom Search API credentials are not configured in .env")

    skills_query = " AND ".join([f'"{skill}"' for skill in req.required_skills[:4]])
    dork_query = f'site:linkedin.com/in/ "{req.job_title}" AND "{req.location}" AND {skills_query}'
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.GOOGLE_CSE_API_KEY,
        "cx": settings.GOOGLE_CSE_CX_ID,
        "q": dork_query,
        "num": req.max_results,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"Google Search API error: {resp.text}")
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
    return results
