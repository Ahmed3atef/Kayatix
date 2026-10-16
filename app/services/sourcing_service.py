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
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-flash-latest",
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
    1. Uses Google Gemini with live Google Search Grounding to discover verified LinkedIn candidate profiles.
    2. If Gemini key is not configured, provides clear guidance to use 1-Click Search or the embedded CSE Web Widget (zero API keys required).
    """
    gemini_key = settings.GEMINI_API_KEY

    # Retrieve credentials from database if missing from runtime config
    if not gemini_key:
        try:
            from sqlalchemy import select
            from app.core.database import AsyncSessionLocal
            from app.models.domain import UserSettings

            async with AsyncSessionLocal() as session:
                stmt = select(UserSettings)
                db_settings = (await session.execute(stmt)).scalars().first()
                if db_settings and db_settings.gemini_api_key:
                    gemini_key = db_settings.gemini_api_key
                    settings.GEMINI_API_KEY = db_settings.gemini_api_key
        except Exception:
            pass

    if not gemini_key:
        logger.warning("[X-Ray Sourcing] Google Gemini API credentials missing.")
        raise ValueError(
            "Google Gemini API key is not configured in Settings / .env for live candidate sourcing. "
            "(Tip: You can use the 1-Click Search on Google button or the CSE Widget without an API key!)"
        )

    logger.info("[X-Ray Sourcing] Using Google Gemini with Google Search Grounding for candidate discovery...")
    return await execute_gemini_grounded_sourcing(req, gemini_key)
