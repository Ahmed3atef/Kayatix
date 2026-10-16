import hashlib
import json
import logging
import re
from typing import Any, List, Optional, Tuple
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from app.core.config import settings
from app.schemas.payloads import CandidateEvaluationResult, InterviewQuestionSchema

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are an elite, unbiased Principal Technical Recruiter and Engineering Manager.
Analyze the provided Candidate Profile (Resume, CV, or Portfolio Website) against the target Job Description.

STRICT EVALUATION RULES:
1. Base all scores and skill matches strictly on evidence present in the text. Do not hallucinate skills.
2. Accurately understand requirement logic:
   - When a job description specifies alternatives (e.g., 'FastAPI or Django', 'TailwindCSS or Bootstrap'), satisfying either alternative meets the requirement.
   - Separate core required competencies from optional/nice-to-have items.
3. Calculate an accurate match_percentage (0 to 100) reflecting genuine role alignment, taking into account required skills, relevant experience tenure, and project accomplishments.
4. Accurately estimate professional years of experience (estimated_years_experience) from work history dates.
5. Identify timeline gaps, job-hopping, or unverified claims under 'red_flags_and_gaps'.
6. Formulate 5 to 7 high-impact, role-tailored interview questions directly testing missing requirements, suspicious claims, and situational technical competence.
7. Return ONLY a valid JSON object matching the exact schema requested.
"""


def compute_request_hash(candidate_text: str, jd_text: str) -> str:
    """Computes a deterministic SHA-256 hash from candidate and JD text."""
    combined = f"{candidate_text.strip()}||{jd_text.strip()}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def _clean_json_string(raw: str) -> str:
    """Strips markdown code blocks and excess whitespace around JSON output."""
    cleaned = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    return cleaned


async def _call_gemini(
    prompt: str,
    response_schema: Any = CandidateEvaluationResult,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> Tuple[str, str]:
    """Primary Provider: Google AI Studio with Native Structured Outputs and auto model fallback."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    preferred_models = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.7-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
    ]
    models_to_try = list(preferred_models)
    try:
        listed = []
        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            actions = getattr(m, "supported_actions", []) or getattr(m, "supported_generation_methods", []) or []
            if actions and "generateContent" not in actions:
                continue
            name_clean = name.replace("models/", "")
            if any(k in name_clean.lower() for k in ["tts", "audio", "embed", "imagen", "realtime", "live", "customtools"]):
                continue
            listed.append(name_clean)
        if listed:
            flash_text = [m for m in listed if "flash" in m.lower()]
            models_to_try = preferred_models + flash_text + listed
    except Exception:
        pass

    seen = set()
    deduped = []
    for m in models_to_try:
        if m not in seen:
            seen.add(m)
            deduped.append(m)

    last_err = None
    for model_name in deduped:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=0.1,
                ),
            )
            if not response.text:
                continue
            return response.text, model_name
        except Exception as err:
            last_err = err
            err_str = str(err).lower()
            if any(k in err_str for k in ["api_key_invalid", "api key not valid", "permission_denied", "consumer_invalid", "consumer_suspended", "unauthenticated", "401"]):
                raise err
            logger.warning("Gemini model %s failed: %s. Trying next available Gemini model.", model_name, err)
            continue
    raise last_err or RuntimeError("Gemini call failed across all candidate models")


async def _call_openai_compatible_provider(
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    response_schema: Any = CandidateEvaluationResult,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> str:
    """Fallback Provider Handler for Groq Cloud and OpenRouter."""
    if not api_key:
        raise ValueError(f"API key missing for model {model_name}")

    schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
    enforced_system = (
        f"{system_instruction}\n\n"
        f"CRITICAL: Your output MUST be a valid JSON object adhering strictly to this JSON Schema:\n{schema_json}"
    )

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": enforced_system},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"Empty response received from {model_name}")
    return content




async def evaluate_candidate(
    candidate_text: str, job_description: str, mode: Optional[str] = None
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Evaluates candidate strictly using the multi-provider Cloud LLM cascade:
    1. Gemini 2.5 Flash -> 2. Groq Llama 3.3 70B -> 3. OpenRouter Llama 3.1 Fallback.
    All candidate analysis, skill matching, YOE estimation, and impact extraction
    are managed 100% by the LLM.
    """
    return await evaluate_candidate_with_fallback(candidate_text, job_description)


async def evaluate_candidate_with_fallback(
    candidate_text: str, job_description: str
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Executes full candidate evaluation across the multi-provider cascade:
    1. Gemini Flash -> 2. Groq Cloud (Fast LPUs) -> 3. OpenRouter Fallback
    """
    user_prompt = (
        f"=== TARGET JOB DESCRIPTION ===\n{job_description}\n\n"
        f"=== CANDIDATE DATA (CV / PORTFOLIO) ===\n{candidate_text}"
    )

    # 1. Try Primary: Gemini
    try:
        gemini_result = await _call_gemini(user_prompt)
        if isinstance(gemini_result, tuple):
            raw_json, model_name = gemini_result
            provider_tag = f"google/{model_name}"
        else:
            raw_json = gemini_result
            provider_tag = "google/gemini-1.5-flash"
        cleaned_json = _clean_json_string(raw_json)
        validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
        return validated, provider_tag
    except Exception as gemini_err:
        logger.warning(
            f"Primary provider (Gemini) failed/throttled: {gemini_err}. Failing over to Groq...")

    # 2. Try Secondary: Groq Cloud (Fast LPUs)
    for groq_model in ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.1-8b-instant", "llama3-70b-8192"]:
        try:
            raw_json = await _call_openai_compatible_provider(
                base_url="https://api.groq.com/openai/v1",
                api_key=settings.GROQ_API_KEY,
                model_name=groq_model,
                prompt=user_prompt,
            )
            cleaned_json = _clean_json_string(raw_json)
            validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
            return validated, f"groq/{groq_model}"
        except Exception as groq_err:
            if "model_not_found" in str(groq_err) or "404" in str(groq_err):
                logger.info(f"Groq {groq_model} not accessible, attempting fallback...")
                continue
            logger.warning(
                f"Secondary provider (Groq {groq_model}) failed/throttled: {groq_err}. Failing over to OpenRouter...")
            break

    # 3. Try Tertiary: OpenRouter Fallback
    for or_model in ["meta-llama/llama-3.1-8b-instruct:free", "meta-llama/llama-3.1-8b-instruct", "meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"]:
        try:
            raw_json = await _call_openai_compatible_provider(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
                model_name=or_model,
                prompt=user_prompt,
            )
            cleaned_json = _clean_json_string(raw_json)
            validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
            slug = or_model.split("/")[-1]
            return validated, f"openrouter/{slug}"
        except Exception as or_err:
            if "404" in str(or_err) or "unavailable for free" in str(or_err):
                continue
            logger.error(f"OpenRouter model {or_model} failed: {or_err}")
            break

    raise RuntimeError("All configured AI providers are currently rate-limited or unavailable.")
