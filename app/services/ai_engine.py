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
from app.services.local_analyzer import local_analyzer

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

SYNTHESIS_SYSTEM_INSTRUCTION = """You are an elite, unbiased Principal Talent Strategist and Interview Architect.
Given a locally parsed candidate profile and the target job description:
1. Formulate 5 to 7 high-impact, role-tailored interview questions focusing specifically on the candidate's missing competencies, unverified claims, and timeline gaps.
2. Provide a 2-3 sentence executive assessment summarizing candidate fit and actionable hiring recommendations.
3. Return ONLY a valid JSON object conforming to the schema requested.
"""


class HybridSynthesisResult(BaseModel):
    executive_summary: str = Field(
        description="2-3 sentence strategic executive summary of candidate fit")
    tailored_interview_questions: List[InterviewQuestionSchema] = Field(
        description="5 to 7 high-depth interview questions directly testing missing requirements, suspicious claims, and practical situational competence"
    )


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
) -> str:
    """Primary Provider: Google AI Studio (Gemini 2.5 Flash) with Native Structured Outputs."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.1,
        ),
    )
    if not response.text:
        raise RuntimeError("Empty response received from Gemini API")
    return response.text


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


async def _generate_dynamic_questions_and_synthesis_from_llm(
    candidate_name: str,
    yoe: float,
    matched_skills: List[str],
    missing_skills: List[str],
    impact_projects: List[str],
    gaps: List[str],
    job_description: str,
) -> Tuple[HybridSynthesisResult, str]:
    """
    Calls cloud LLM cascade using a compact structured prompt (saving ~90% of tokens).
    Generates dynamic role-specific interview questions and executive synthesis.
    """
    impacts_formatted = "\n".join(
        f"- {p}" for p in impact_projects[:4]) if impact_projects else "None provided"
    gaps_formatted = "\n".join(
        f"- {g}" for g in gaps) if gaps else "None detected"

    prompt = (
        f"=== TARGET JOB DESCRIPTION ===\n{job_description}\n\n"
        f"=== CANDIDATE PROFILE (STRUCTURED LOCAL EXTRACTION) ===\n"
        f"Candidate Name: {candidate_name}\n"
        f"Years of Experience: {yoe}\n"
        f"Verified Matched Skills: {', '.join(matched_skills) if matched_skills else 'None verified'}\n"
        f"Missing Critical Requirements: {', '.join(missing_skills) if missing_skills else 'None missing'}\n\n"
        f"Quantified Impact & Deliverables:\n{impacts_formatted}\n\n"
        f"Career Continuity & Timeline Gaps:\n{gaps_formatted}\n\n"
        f"TASK: Generate 5-7 challenging, tailored interview questions probing the missing requirements and gaps, "
        f"plus a 2-3 sentence executive summary assessment."
    )

    # 1. Primary: Gemini 2.5 Flash
    try:
        raw_json = await _call_gemini(
            prompt=prompt,
            response_schema=HybridSynthesisResult,
            system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION,
        )
        cleaned = _clean_json_string(raw_json)
        validated = HybridSynthesisResult.model_validate_json(cleaned)
        return validated, "google/gemini-2.5-flash"
    except Exception as gemini_err:
        logger.warning(
            f"Hybrid synthesis with Gemini failed: {gemini_err}. Failing over to Groq...")

    # 2. Secondary: Groq Llama 3.3 70B
    try:
        raw_json = await _call_openai_compatible_provider(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
            model_name="llama-3.3-70b-versatile",
            prompt=prompt,
            response_schema=HybridSynthesisResult,
            system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION,
        )
        cleaned = _clean_json_string(raw_json)
        validated = HybridSynthesisResult.model_validate_json(cleaned)
        return validated, "groq/llama-3.3-70b-versatile"
    except Exception as groq_err:
        logger.warning(
            f"Hybrid synthesis with Groq failed: {groq_err}. Failing over to OpenRouter...")

    # 3. Tertiary: OpenRouter
    try:
        raw_json = await _call_openai_compatible_provider(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            model_name="meta-llama/llama-3.1-8b-instruct:free",
            prompt=prompt,
            response_schema=HybridSynthesisResult,
            system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION,
        )
        cleaned = _clean_json_string(raw_json)
        validated = HybridSynthesisResult.model_validate_json(cleaned)
        return validated, "openrouter/llama-3.1-8b-instruct:free"
    except Exception as or_err:
        logger.error(f"All providers exhausted for hybrid synthesis: {or_err}")
        raise RuntimeError(
            "Cloud LLM providers unavailable for dynamic synthesis.")


async def evaluate_candidate(
    candidate_text: str, job_description: str, mode: Optional[str] = None
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Evaluates candidate according to the active configuration mode:
    - 'local_offline': 100% zero-quota local analysis with smart extraction.
    - 'llm_cascade': Full cloud multi-provider LLM cascade.
    - 'hybrid' (Default): Zero-quota local extraction + compact LLM call for dynamic questions & synthesis.
      Falls back gracefully to local baseline questions if offline or rate-limited.
    """
    active_mode = mode or settings.EVALUATION_MODE

    # 1. 100% Offline Local Engine
    if active_mode == "local_offline":
        raw_local = local_analyzer.evaluate(candidate_text, job_description)
        validated = CandidateEvaluationResult.model_validate(raw_local)
        return validated, "local_engine"

    # 2. Cloud LLM Cascade
    if active_mode == "llm_cascade":
        return await evaluate_candidate_with_fallback(candidate_text, job_description)

    # 3. Hybrid Mode (Recommended Default)
    raw_local = local_analyzer.evaluate(candidate_text, job_description)
    try:
        synthesis, provider = await _generate_dynamic_questions_and_synthesis_from_llm(
            candidate_name=raw_local["candidate_name"],
            yoe=raw_local["estimated_years_experience"],
            matched_skills=raw_local["matched_skills"],
            missing_skills=raw_local["missing_critical_skills"],
            impact_projects=raw_local["detected_projects_and_impact"],
            gaps=raw_local["red_flags_and_gaps"],
            job_description=job_description,
        )
        raw_local["executive_summary"] = synthesis.executive_summary
        raw_local["tailored_interview_questions"] = [
            q.model_dump() for q in synthesis.tailored_interview_questions
        ]
        validated = CandidateEvaluationResult.model_validate(raw_local)
        return validated, f"hybrid (local + {provider})"
    except Exception as llm_err:
        logger.warning(
            f"Hybrid LLM synthesis failed or rate-limited ({llm_err}). Falling back to local questions."
        )
        validated = CandidateEvaluationResult.model_validate(raw_local)
        return validated, "hybrid (local_engine)"


async def evaluate_candidate_with_fallback(
    candidate_text: str, job_description: str
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Executes full candidate evaluation across the multi-provider cascade:
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
        logger.warning(
            f"Primary provider (Gemini) failed/throttled: {gemini_err}. Failing over to Groq...")

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
        logger.warning(
            f"Secondary provider (Groq) failed/throttled: {groq_err}. Failing over to OpenRouter...")

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
        raise RuntimeError(
            "All configured AI providers are currently rate-limited or unavailable.")
