import json
import logging
import re
from typing import List, Optional
import httpx
from app.core.config import settings
from app.schemas.payloads import XRaySearchRequest, XRayProfileItem

logger = logging.getLogger("kayatix.sourcing")


def _clean_json_string(raw: str) -> str:
    cleaned = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    return cleaned


async def execute_gemini_grounded_sourcing(req: XRaySearchRequest, gemini_key: str) -> List[XRayProfileItem]:
    """
    Modern Google Cloud Alternative:
    Uses Google Gemini with native Google Search Grounding to discover publicly indexed LinkedIn profiles
    without needing the legacy Custom Search JSON API.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_key)
    skills_str = ", ".join(req.required_skills[:5])
    dork_query = f'site:linkedin.com/in/ "{req.job_title}" AND "{req.location}" AND {skills_str}'

    prompt = f"""You are an elite technical talent sourcing assistant.
Perform a Google Search to discover public LinkedIn profiles of candidates matching this query:
{dork_query}

Target Role: {req.job_title}
Location: {req.location}
Required Skills: {skills_str}

Find up to {req.max_results} real candidate LinkedIn profiles.
Return ONLY a valid JSON array of objects with the exact keys:
[
  {{
    "full_title": "Candidate Name - Current Headline or Role at Company | LinkedIn",
    "linkedin_url": "https://www.linkedin.com/in/candidate-slug",
    "snippet": "Short summary of candidate's technical skills, experience tenure, and current role"
  }}
]
Do not include any explanation or markdown formatting, output raw JSON array.
"""
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1,
    )

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    last_err = None
    for model_name in models_to_try:
        try:
            logger.info(f"[X-Ray Sourcing] Querying Gemini ({model_name}) with Google Search Grounding...")
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            raw_text = resp.text or ""
            cleaned = _clean_json_string(raw_text)
            candidates_data = json.loads(cleaned)

            if isinstance(candidates_data, list) and candidates_data:
                results: List[XRayProfileItem] = []
                for item in candidates_data[:req.max_results]:
                    results.append(
                        XRayProfileItem(
                            full_title=item.get("full_title", "LinkedIn Candidate"),
                            linkedin_url=item.get("linkedin_url", "https://www.linkedin.com"),
                            snippet=item.get("snippet", ""),
                        )
                    )
                logger.info(f"[X-Ray Sourcing] Gemini Search Grounding successfully discovered {len(results)} candidate(s).")
                return results
        except Exception as e:
            logger.warning(f"[X-Ray Sourcing] Gemini model {model_name} search grounding failed: {e}")
            last_err = e
            continue

    raise ValueError(f"Gemini AI Sourcing could not retrieve profiles: {last_err}")


async def execute_linkedin_xray_search(req: XRaySearchRequest) -> List[XRayProfileItem]:
    """
    Sourcing Pipeline:
    1. Tries Google Custom Search API if configured.
    2. If Google Cloud returns 403 (legacy Custom Search JSON API restricted for new projects),
       automatically falls back to Google Gemini with live Google Search Grounding.
    3. If neither is available, provides clear guidance to use the 1-Click Search or CSE Web Widget.
    """
    api_key = settings.GOOGLE_CSE_API_KEY
    cx_id = settings.GOOGLE_CSE_CX_ID
    gemini_key = settings.GEMINI_API_KEY

    # Retrieve credentials from database if missing from runtime config
    if not (api_key and cx_id) or not gemini_key:
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
                    gemini_key = gemini_key or db_settings.gemini_api_key
                    if db_settings.google_cse_api_key:
                        settings.GOOGLE_CSE_API_KEY = db_settings.google_cse_api_key
                    if db_settings.google_cse_cx_id:
                        settings.GOOGLE_CSE_CX_ID = db_settings.google_cse_cx_id
                    if db_settings.gemini_api_key:
                        settings.GEMINI_API_KEY = db_settings.gemini_api_key
        except Exception:
            pass

    if not (api_key and cx_id) and not gemini_key:
        logger.warning("[X-Ray Sourcing] Google Custom Search credentials missing.")
        raise ValueError(
            "Google Custom Search API credentials are not configured in Settings / .env. "
            "(Tip: You can use the 1-Click Search on Google button or the CSE Widget without an API key!)"
        )

    # Method A: Google Custom Search JSON API
    if api_key and cx_id:
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
            if resp.status_code == 200:
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
                logger.info(f"[X-Ray Sourcing] Successfully retrieved {len(results)} candidate profile(s) via Google CSE.")
                return results

            err_text = resp.text
            logger.error(f"[X-Ray Sourcing] Google Search API error (HTTP {resp.status_code}): {err_text}")

            # If new project restriction is hit, and gemini_key available, try modern Gemini Grounded Search
            if ("does not have the access to Custom Search JSON API" in err_text or "PERMISSION_DENIED" in err_text or resp.status_code == 403) and gemini_key:
                logger.info(
                    "[X-Ray Sourcing] Legacy Custom Search JSON API restricted for this project. "
                    "Automatically switching to modern Google Gemini with Google Search Grounding..."
                )
                try:
                    return await execute_gemini_grounded_sourcing(req, gemini_key)
                except Exception as gemini_err:
                    logger.warning(f"[X-Ray Sourcing] Gemini Search Grounding fallback failed: {gemini_err}")

            if "does not have the access to Custom Search JSON API" in err_text:
                raise ValueError(
                    "Google has restricted the legacy Custom Search JSON API for newly created Google Cloud projects "
                    "('This project does not have the access to Custom Search JSON API'). "
                    "Google no longer grants new projects access to this legacy API. "
                    "Please use the '1-Click Search on Google' button or the 'CSE Widget' tab to source candidates instantly with zero API keys."
                )
            if "API_KEY_SERVICE_BLOCKED" in err_text or "PERMISSION_DENIED" in err_text:
                raise ValueError(
                    "Google Search API error: Requests to Custom Search are blocked (PERMISSION_DENIED / API_KEY_SERVICE_BLOCKED). "
                    "Please check your Google Cloud Console project restrictions, or use the '1-Click Search on Google' button or 'CSE Widget' tab."
                )
            raise ValueError(f"Google Search API error: {err_text}")

    # Method B: Direct Gemini Google Search Grounding (if no CSE keys)
    if gemini_key:
        logger.info("[X-Ray Sourcing] Using Google Gemini with Google Search Grounding for candidate discovery...")
        return await execute_gemini_grounded_sourcing(req, gemini_key)

    raise ValueError(
        "Google Custom Search API credentials are not configured in Settings / .env. "
        "(Tip: You can use the 1-Click Search on Google button or the CSE Widget without an API key!)"
    )
