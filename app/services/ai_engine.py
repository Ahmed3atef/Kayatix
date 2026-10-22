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

SYSTEM_INSTRUCTION = """You are a calibrated Principal Technical Bar Raiser and Engineering Director conducting a rigorous, evidence-anchored candidate evaluation.
You evaluate the candidate profile directly against the target Job Description based on verifiable technical skills, production project complexity, and measurable impact.

EVALUATION METHODOLOGY & CHAIN-OF-THOUGHT (CoT):
1. IDENTITY & CONTACT EXTRACTION:
   - Extract the candidate's real legal full name from the top header or contact details. Avoid generic labels like 'Candidate Profile' whenever a name is present.

2. TENURE & CHRONOLOGICAL AUDIT:
   - Accurately calculate 'estimated_years_experience' based SOLELY on commercial software engineering roles.
   - Distinctly differentiate technical engineering tenure from unrelated employment (e.g., retail, sales, non-technical support). Do not count non-technical roles toward engineering YOE.
   - Scrutinize date ranges for timeline gaps > 6 months, future-dated claims, or rapid job-hopping (< 6 months per role).

3. REQUIREMENT ALIGNMENT & BOOLEAN REASONING:
   - When the JD specifies alternatives (e.g., 'FastAPI or Django', 'PostgreSQL or MySQL'), fulfilling either alternative fully satisfies the requirement.
   - Separate non-negotiable core competencies from optional 'nice-to-have' preferences.
   - Differentiate between passive keyword listings in a 'Skills' block vs active verified implementation in 'Projects' or 'Work Experience'.

4. CALIBRATED SCORING RUBRIC (match_percentage: 0 to 100):
   - 85 - 100%: Exceptional Fit. Exceeds mandatory requirements, matches expected seniority, demonstrates proven production scale.
   - 70 - 84%: Strong Hireable Fit. Meets all core technical criteria with relevant tenure; minor gaps only in secondary tools.
   - 50 - 69%: Moderate Fit / Development Opportunity. Strong foundational skills, but junior tenure applying for a senior role or lacks key architectural stack depth.
   - 0 - 49%: Low Fit. Critical stack mismatch, severe experience deficit, or unverifiable claims.

5. STRATEGIC INTERVIEW QUESTION GENERATION:
   - Generate 5 to 7 concrete, high-signal questions across Technical, System Design, Behavioral, and Gap-Verification.
   - Anchor questions in the candidate's actual projects (e.g., reference specific systems, databases, or trade-offs mentioned in their resume).
   - Probe identified missing critical skills with direct implementation scenarios.

OUTPUT MANDATE:
- Return ONLY valid JSON adhering strictly to the requested response schema.
- No conversational prelude, no markdown wrapping, no hallucinated competencies.
"""


# ==============================================================================
# EVALUATION PROMPT CONSTRUCTION
# ==============================================================================

def build_evaluation_prompt(candidate_text: str, job_description: str) -> str:
    """
    Constructs a calibrated evaluation prompt combining the candidate's resume/portfolio
    with the target job description requirements.
    """
    return f"""### TARGET ROLE REQUIREMENTS & BENCHMARK
{job_description.strip()}

---
### CANDIDATE RESUME & PORTFOLIO
{candidate_text.strip()}
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
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-flash-latest",
    ]
    deduped = preferred_models

    last_err = None
    for model_name in deduped:
        try:
            logger.info(f"[AI Engine] Querying Google Gemini model '{model_name}'...")
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
            logger.info(f"[AI Engine] Google Gemini model '{model_name}' generated structured response ({len(response.text)} chars).")
            return response.text, model_name
        except Exception as err:
            last_err = err
            err_str = str(err).lower()
            if any(k in err_str for k in ["api_key_invalid", "api key not valid", "permission_denied", "consumer_invalid", "consumer_suspended", "unauthenticated", "401"]):
                raise err
            logger.warning("[AI Engine] Gemini model %s failed: %s. Trying next available Gemini model.", model_name, err)
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
    """Fallback Provider Handler for Groq Cloud and Ollama Cloud."""
    if not api_key:
        raise ValueError(f"API key missing for model {model_name}")

    schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
    enforced_system = (
        f"{system_instruction}\n\n"
        f"CRITICAL: Your output MUST be a valid JSON object adhering strictly to this JSON Schema:\n{schema_json}"
    )

    logger.info(f"[AI Engine] Querying provider ({base_url}) with model '{model_name}'...")
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
    logger.info(f"[AI Engine] Model '{model_name}' generated structured response ({len(content)} chars).")
    return content




async def evaluate_candidate(
    candidate_text: str,
    job_description: str,
    mode: Optional[str] = None,
    db: Optional[Any] = None,
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Evaluates candidate strictly using the multi-provider Cloud LLM cascade.
    """
    return await evaluate_candidate_with_fallback(candidate_text, job_description, db=db)


async def evaluate_candidate_with_fallback(
    candidate_text: str,
    job_description: str,
    db: Optional[Any] = None,
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Executes full candidate evaluation across the multi-provider cascade:
    1. Builds calibrated evaluation prompt.
    2. Multi-provider cascade: Gemini -> Groq -> Ollama Cloud.
    """
    user_prompt = build_evaluation_prompt(candidate_text, job_description)

    # 1. Try Primary: Gemini
    try:
        gemini_result = await _call_gemini(user_prompt, system_instruction=SYSTEM_INSTRUCTION)
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

    # 3. Try Secondary: Groq Cloud (Fast LPUs)
    for groq_model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama3-70b-8192"]:
        try:
            raw_json = await _call_openai_compatible_provider(
                base_url="https://api.groq.com/openai/v1",
                api_key=settings.GROQ_API_KEY,
                model_name=groq_model,
                prompt=user_prompt,
                system_instruction=SYSTEM_INSTRUCTION,
            )
            cleaned_json = _clean_json_string(raw_json)
            validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
            return validated, f"groq/{groq_model}"
        except Exception as groq_err:
            if "model_not_found" in str(groq_err) or "404" in str(groq_err):
                logger.info(f"Groq {groq_model} not accessible, attempting fallback...")
                continue
            logger.warning(
                f"Secondary provider (Groq {groq_model}) failed/throttled: {groq_err}. Failing over to Ollama Cloud...")
            break
    # 3. Try Tertiary: Ollama Cloud Models Pool Fallback (Free Tier: gpt-oss:120b, gpt-oss:20b, gemma4:31b, nemotron-3-nano:30b, nemotron-3-super, nemotron-3-ultra, beam)
    if settings.OLLAMA_API_KEY and settings.OLLAMA_API_KEY.strip():
        ollama_models = [
            "gpt-oss:120b",
            "gpt-oss:20b",
            "gemma4:31b",
            "nemotron-3-nano:30b",
            "nemotron-3-super",
            "nemotron-3-ultra",
            "beam",
        ]
        base_url = (settings.OLLAMA_BASE_URL or "https://ollama.com/v1").rstrip("/")
        for o_model in ollama_models:
            try:
                raw_json = await _call_openai_compatible_provider(
                    base_url=base_url,
                    api_key=settings.OLLAMA_API_KEY.strip(),
                    model_name=o_model,
                    prompt=user_prompt,
                    system_instruction=SYSTEM_INSTRUCTION,
                )
                cleaned_json = _clean_json_string(raw_json)
                validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
                return validated, f"ollama/{o_model}"
            except Exception as o_err:
                logger.warning(f"Ollama model {o_model} failed/throttled: {o_err}. Continuing cascade...")
                continue

    raise RuntimeError("All configured AI providers are currently rate-limited or unavailable.")
