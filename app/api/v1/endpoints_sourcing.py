from typing import List
from fastapi import APIRouter, HTTPException
from app.schemas.payloads import XRaySearchRequest, XRayProfileItem
from app.services.sourcing_service import execute_linkedin_xray_search

router = APIRouter(prefix="/api/v1/sourcing", tags=["Legal LinkedIn Sourcing"])


@router.post("/linkedin-xray", response_model=List[XRayProfileItem])
async def discover_candidates_via_xray(payload: XRaySearchRequest):
    """
    Discovers public LinkedIn profiles matching role, skills, and location
    using Google X-Ray search without scraping LinkedIn directly.
    """
    try:
        profiles = await execute_linkedin_xray_search(payload)
        return profiles
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
