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

SYSTEM_INSTRUCTION = """You are an elite Senior Talent Acquisition Director and Principal Technical Bar Raiser with 15+ years of executive and senior engineering hiring experience.
You conduct rigorous, evidence-based, unbiased candidate evaluations benchmarked against the target Job Description (JD).
You DO NOT perform superficial keyword counting. You evaluate depth of competency, verified production impact, seniority calibration, and career trajectory.

════════════════════════════════════════════════════════════════════════════════
SENIOR HR EVALUATION FRAMEWORK & CHAIN-OF-THOUGHT (CoT)
════════════════════════════════════════════════════════════════════════════════

1. CANDIDATE PROFILE AUDIT & COMMERCIAL EXPERIENCE:
   - Extract the candidate's actual legal full name from header or contact sections (never use generic placeholders if a name is visible).
   - Accurately calculate 'estimated_years_experience' based STRICTLY on professional/commercial experience relevant to the role.
   - Exclude non-relevant employment (retail, short non-technical internships, customer support) from engineering/specialist YOE.
   - Differentiate hands-on production engineering from academic coursework or student projects.

2. COMPETENCY VERIFICATION (MUST-HAVES vs. NICE-TO-HAVES):
   - Categorize JD requirements into:
     * Non-Negotiable Core (P0): Core language/framework, required seniority, essential domain fundamentals.
     * Preferred / Secondary (P1): Adjacent tools, specific cloud platforms, CI/CD, secondary libraries.
     * Nice-to-Have (P2): Optional certifications, bonus domain exposure.
   - For JD alternatives (e.g. 'PostgreSQL or MySQL', 'AWS or GCP', 'FastAPI or Django'), fulfilling either alternative fully satisfies the requirement.
   - Verified Evidence vs Buzzword Stuffing:
     * A skill listed only in a 'Skills Summary' but NEVER mentioned in any work experience or project is unverified (penalize in scoring).
     * A skill tied to concrete project achievements, architecture decisions, and metrics is verified.

3. CALIBRATED 100-POINT SENIOR HR MATCHING RUBRIC:
   Evaluate candidate against this 100-point weighted framework:
   * Core Competency & Stack Fit (Max 40 pts):
     - 35-40: Complete mastery of core mandatory stack with deep production track record.
     - 25-34: Proficient in most core competencies; minor ramp-up needed on secondary tool.
     - 15-24: Partial overlap (knows language but lacks framework or ecosystem depth).
     - 0-14: Fundamental stack mismatch (wrong core tech stack).
   * Seniority & Scope Alignment (Max 25 pts):
     - 20-25: Tenure and demonstrated scope of ownership match or exceed role expectations (e.g., senior leads design, mid delivers independently).
     - 14-19: Slightly junior for the title but demonstrates strong velocity and trajectory.
     - 5-13: Significant seniority gap (e.g. 2 YOE applying for a 7+ YOE Staff/Lead position).
   * Verifiable Business & Technical Impact (Max 20 pts):
     - 16-20: Outstanding STAR-format achievements with quantifiable metrics (scale, RPS, latency, cost, revenue, team leadership).
     - 10-15: Clear deliverables and ownership, mostly qualitative descriptions.
     - 0-9: Passive job descriptions ('responsible for maintenance') with zero measurable impact.
   * Secondary Tools & Architectural Breadth (Max 10 pts):
     - 8-10: Strong grasp of distributed systems, testing, containerization, observability, and modern DevOps.
     - 4-7: Basic working knowledge of standard tooling.
   * Career Stability & Trajectory (Max 5 pts):
     - 5: Healthy tenure (avg 1.5-3+ years per role), consistent progression in responsibility.
     - 0-3: Multiple consecutive short stints (<9 months without justification) or unaddressed long gaps.

   TOTAL SCORE = Core (0-40) + Seniority (0-25) + Impact (0-20) + Secondary (0-10) + Stability (0-5).
   Clamp between 0 and 100.

4. HIRING RECOMMENDATION & EXECUTIVE SUMMARY:
   Assign an explicit hiring recommendation:
   - 'Strong Hire': Score 85-100. Outstanding candidate exceeding benchmarks; prioritize immediate interview.
   - 'Proceed (Technical Screen)': Score 70-84. Meets all core requirements; verify specific secondary areas.
   - 'Borderline (Phone Screen First)': Score 50-69. Potential fit with notable gaps in seniority or stack; quick screen recommended.
   - 'Reject / Not Recommended': Score 0-49. Major disqualifying deficit in core stack or experience.

   The Executive Summary MUST be 2-4 sentences, written in the voice of a Senior HR Leader:
   * Start with the recommendation tag: e.g., '[STRONG HIRE]', '[PROCEED - TECH SCREEN]', '[BORDERLINE]', or '[REJECT]'.
   * State candidate's total relevant commercial YOE, primary domain expertise, and core strengths.
   * Specify exact trade-offs, critical gaps, or compensation/seniority calibration notes.
   * Provide the clear next step for the hiring team.

5. RED FLAGS & TIMELINE AUDIT:
   Identify specific, professional observations (not vague criticism):
   * Employment timeline gaps > 6 months (exact dates noted).
   * High job-hopping velocity (e.g., 3+ roles in 2 years with <8 months tenure each).
   * Unsubstantiated buzzword claims (technologies listed in skills but absent from all project descriptions).
   * Title inflation (e.g., 'Lead Architect' with under 2 years total experience).
   * If no red flags exist, return an empty array or a clear note: 'No major timeline or credential anomalies detected.'

6. TAILORED HIGH-SIGNAL INTERVIEW QUESTIONS:
   Generate 5 to 7 incisive, scenario-grounded questions across:
   * Technical Deep-Dive: Directly question a complex claim from their resume.
   * System Design & Architecture: Scale, trade-offs, and resilience tailored to their past projects.
   * Behavioral (STAR Method): Conflict resolution, technical debt management, or ownership under pressure.
   * Gap Verification: Targeted scenario probing an unverified skill or missing requirement.
   For each question:
   * 'target_area': Exact skill, claim, or gap being tested.
   * 'expected_answer_criteria': Specific technical keywords, architectural patterns, and behavioral green flags the interviewer should listen for.

OUTPUT MANDATE:
- Return ONLY valid JSON adhering strictly to the requested response schema.
- No conversational prelude, no markdown wrapping, no hallucinated competencies.
"""


# ==============================================================================
# EVALUATION PROMPT CONSTRUCTION
# ==============================================================================

def build_evaluation_prompt(candidate_text: str, job_description: str) -> str:
    """
    Constructs a calibrated Senior HR evaluation prompt combining the candidate's resume/portfolio
    with the target job description requirements, instructing the model to apply the 100-point rubric.
    """
    return f"""### TARGET ROLE REQUIREMENTS & BENCHMARK
{job_description.strip()}

---
### CANDIDATE RESUME & PORTFOLIO
{candidate_text.strip()}

---
### SENIOR HR EVALUATION INSTRUCTIONS:
1. Identify the role's Core Must-Haves (P0) vs Secondary Preferences (P1/P2).
2. Calculate verified commercial engineering/specialist years of experience (exclude unrelated work).
3. Apply the 100-Point Senior HR Evaluation Framework:
   - Core Competency & Stack Alignment (0 to 40 pts)
   - Seniority & Scope of Ownership (0 to 25 pts)
   - Measurable Business & Technical Impact (0 to 20 pts)
   - Secondary Tools & System Design Breadth (0 to 10 pts)
   - Career Stability & Trajectory (0 to 5 pts)
   Sum these components to determine 'match_percentage' (0-100).
4. Provide a Senior HR Executive Summary starting with an explicit recommendation tag ([STRONG HIRE], [PROCEED - TECH SCREEN], [BORDERLINE], or [REJECT]).
5. Uncover genuine timeline gaps, job-hopping velocity, or unverified claims for 'red_flags_and_gaps'.
6. Craft 5 to 7 incisive, project-anchored interview questions with concrete evaluation criteria.
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
