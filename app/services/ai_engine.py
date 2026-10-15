import hashlib
import json
import logging
import re
from typing import Tuple
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from app.core.config import settings
from app.schemas.payloads import CandidateEvaluationResult

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are an elite, unbiased Principal Technical Recruiter and Engineering Manager.
Analyze the provided Candidate Profile (Resume or Portfolio Website) against the target Job Description.

STRICT EVALUATION RULES:
1. Base all scores and skill matches strictly on evidence present in the text. Do not hallucinate skills.
2. Differentiate between passive keyword mention and proven project experience.
3. Identify timeline gaps, job-hopping, or vague buzzword usage under 'red_flags_and_gaps'.
4. Create highly specific interview questions that test missing skills or probe suspicious claims.
5. Return ONLY a valid JSON object matching the exact schema requested.
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


async def _call_gemini(prompt: str) -> str:
    """Primary Provider: Google AI Studio (Gemini 2.5 Flash) with Native Structured Outputs."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=CandidateEvaluationResult,
            temperature=0.1,
        ),
    )
    if not response.text:
        raise RuntimeError("Empty response received from Gemini API")
    return response.text


async def _call_openai_compatible_provider(
    base_url: str, api_key: str, model_name: str, prompt: str
) -> str:
    """Fallback Provider Handler for Groq Cloud and OpenRouter."""
    if not api_key:
        raise ValueError(f"API key missing for model {model_name}")

    schema_json = json.dumps(CandidateEvaluationResult.model_json_schema(), indent=2)
    enforced_system = (
        f"{SYSTEM_INSTRUCTION}\n\n"
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


async def evaluate_candidate_with_fallback(
    candidate_text: str, job_description: str
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Executes candidate evaluation across the multi-provider cascade:
    1. Gemini 2.5 Flash -> 2. Groq Llama 3.3 70B -> 3. OpenRouter Llama 3.1 Fallback
    """
    user_prompt = (
        f"=== TARGET JOB DESCRIPTION ===\n{job_description}\n\n"
        f"=== CANDIDATE DATA (CV / PORTFOLIO) ===\n{candidate_text}"
    )

    # 1. Try Primary: Gemini 2.5 Flash
    try:
        raw_json = await _call_gemini(user_prompt)
        cleaned_json = _clean_json_string(raw_json)
        validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
        return validated, "google/gemini-2.5-flash"
    except Exception as gemini_err:
        logger.warning(f"Primary provider (Gemini) failed/throttled: {gemini_err}. Failing over to Groq...")

    # 2. Try Secondary: Groq Cloud (Llama 3.3 70B)
    try:
        raw_json = await _call_openai_compatible_provider(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
            model_name="llama-3.3-70b-versatile",
            prompt=user_prompt,
        )
        cleaned_json = _clean_json_string(raw_json)
        validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
        return validated, "groq/llama-3.3-70b-versatile"
    except Exception as groq_err:
        logger.warning(f"Secondary provider (Groq) failed/throttled: {groq_err}. Failing over to OpenRouter...")

    # 3. Try Tertiary: OpenRouter Fallback
    try:
        raw_json = await _call_openai_compatible_provider(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            model_name="meta-llama/llama-3.1-8b-instruct:free",
            prompt=user_prompt,
        )
        cleaned_json = _clean_json_string(raw_json)
        validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
        return validated, "openrouter/llama-3.1-8b-instruct:free"
    except Exception as or_err:
        logger.error(f"All AI providers exhausted: {or_err}")
        raise RuntimeError("All configured AI providers are currently rate-limited or unavailable.")
