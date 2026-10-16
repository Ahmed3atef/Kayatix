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
You evaluate the candidate profile using Retrieval-Augmented Generation (RAG) evidence segments extracted from their resume/portfolio against the target Job Description.

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
# RETRIEVAL-AUGMENTED GENERATION (RAG) CONTEXT EXTRACTION & CHUNKING
# ==============================================================================

def segment_candidate_profile(raw_text: str) -> dict[str, str]:
    """
    RAG Stage 1 - Semantic Document Chunking:
    Parses unstructured resume / portfolio text into categorized functional blocks:
    - technical_skills: Programming languages, frameworks, DBs, cloud tools
    - professional_experience: Roles, company tenures, chronological dates
    - engineering_projects: Architected systems, metrics, repositories
    - education_certifications: Academic credentials, courses, degrees
    - candidate_summary: Bio, headline, contact info
    """
    sections: dict[str, list[str]] = {
        "candidate_summary": [],
        "technical_skills": [],
        "professional_experience": [],
        "engineering_projects": [],
        "education_certifications": [],
    }
    current_section = "candidate_summary"

    for line in raw_text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue

        clean_heading = re.sub(r"[^a-zA-Z\s]", "", trimmed).strip().upper()

        if any(h == clean_heading or clean_heading.startswith(h) for h in [
            "SKILLS", "TECHNICAL SKILLS", "TECH STACK", "CORE COMPETENCIES", "TECHNOLOGIES", "TOOLS"
        ]):
            current_section = "technical_skills"
            continue
        elif any(h == clean_heading or clean_heading.startswith(h) for h in [
            "EXPERIENCE", "WORK EXPERIENCE", "EMPLOYMENT HISTORY", "PROFESSIONAL EXPERIENCE", "CAREER HISTORY"
        ]):
            current_section = "professional_experience"
            continue
        elif any(h == clean_heading or clean_heading.startswith(h) for h in [
            "PROJECTS", "KEY PROJECTS", "PERSONAL PROJECTS", "PORTFOLIO", "OPEN SOURCE", "SELECTED WORK"
        ]):
            current_section = "engineering_projects"
            continue
        elif any(h == clean_heading or clean_heading.startswith(h) for h in [
            "EDUCATION", "ACADEMIC BACKGROUND", "CERTIFICATIONS", "COURSES", "TRAINING"
        ]):
            current_section = "education_certifications"
            continue

        sections[current_section].append(trimmed)

    return {k: "\n".join(v) for k, v in sections.items()}


def extract_jd_core_facets(jd_text: str) -> dict[str, str]:
    """
    RAG Stage 2 - Target Requirement Decomposition:
    Extracts core competency facets from the target Job Description:
    - Core technical stack requirements
    - Seniority and experience expectations
    - Architectural scale and responsibilities
    """
    must_haves: list[str] = []
    nice_to_haves: list[str] = []
    responsibilities: list[str] = []

    current_facet = must_haves
    for line in jd_text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        lower_line = trimmed.lower()
        if any(term in lower_line for term in ["nice to have", "plus", "preferred", "bonus", "optional"]):
            current_facet = nice_to_haves
        elif any(term in lower_line for term in ["responsibilit", "what you will do", "duties", "role overview"]):
            current_facet = responsibilities
        elif any(term in lower_line for term in ["requirement", "qualification", "must have", "must-have", "skills"]):
            current_facet = must_haves

        current_facet.append(trimmed)

    return {
        "core_requirements": "\n".join(must_haves) if must_haves else jd_text[:1200],
        "nice_to_haves": "\n".join(nice_to_haves) if nice_to_haves else "Not explicitly differentiated; evaluate against core requirements.",
        "responsibilities": "\n".join(responsibilities) if responsibilities else "General backend engineering delivery",
    }


def build_rag_augmented_prompt(
    candidate_text: str, job_description: str, rag_template: Optional[str] = None
) -> str:
    """
    RAG Stage 3 - Augmented Generation Context Construction:
    Combines semantic chunks, requirement facets, and provenance verification
    into a calibrated, high-precision prompt using database template if provided.
    """
    segments = segment_candidate_profile(candidate_text)
    jd_facets = extract_jd_core_facets(job_description)

    mapping = {
        "core_requirements": jd_facets['core_requirements'],
        "nice_to_haves": jd_facets['nice_to_haves'],
        "responsibilities": jd_facets['responsibilities'],
        "technical_skills": segments['technical_skills'] or 'Refer to full candidate profile below',
        "professional_experience": segments['professional_experience'] or 'Refer to full candidate profile below',
        "engineering_projects": segments['engineering_projects'] or 'Refer to full candidate profile below',
        "education_certifications": segments['education_certifications'] or 'Not provided',
        "candidate_text": candidate_text,
    }

    if rag_template:
        try:
            return rag_template.format(**mapping)
        except Exception as e:
            logger.warning(f"[AI Engine] Error formatting custom RAG template: {e}. Falling back to default format.")

    return f"""### TARGET ROLE REQUIREMENTS & BENCHMARK
[Core Mandatory Qualifications & Stack]:
{mapping['core_requirements']}

[Preferred / Secondary Skills]:
{mapping['nice_to_haves']}

[Role Scope & Responsibilities]:
{mapping['responsibilities']}

---
### RAG RETRIEVED CANDIDATE EVIDENCE MATRIX
[Candidate Skills & Tools Chunk]:
{mapping['technical_skills']}

[Professional Experience & Tenures Chunk]:
{mapping['professional_experience']}

[Key Projects & Engineering Artifacts Chunk]:
{mapping['engineering_projects']}

[Education & Credentials Chunk]:
{mapping['education_certifications']}

---
### FULL CANDIDATE VERBATIM PROVENANCE
{candidate_text}
"""


async def get_active_ai_instruction(db: Optional[Any] = None) -> Tuple[str, str]:
    """
    Reads the active RAG prompt template and AI system instruction from the database
    BEFORE any AI API call is executed.
    If database record is not present, seeds it from rag_ai_instructions.json.
    Falls back gracefully to the JSON schema file if database is unreachable.
    Returns: (system_instruction, rag_prompt_template).
    """
    from sqlalchemy import select
    from app.models.domain import AIInstruction
    from app.services.settings_service import load_rag_ai_instructions_schema, sync_ai_instructions_to_database

    if db is not None:
        try:
            stmt = select(AIInstruction).where(AIInstruction.name == "default_evaluator")
            result = await db.execute(stmt)
            inst = result.scalar_one_or_none()
            if inst:
                return inst.system_instruction, inst.rag_prompt_template
            synced_inst = await sync_ai_instructions_to_database(db)
            return synced_inst.system_instruction, synced_inst.rag_prompt_template
        except Exception as e:
            logger.warning(f"[AI Engine] Error reading AI instruction from db session: {e}. Trying fallback.")

    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            stmt = select(AIInstruction).where(AIInstruction.name == "default_evaluator")
            result = await session.execute(stmt)
            inst = result.scalar_one_or_none()
            if inst:
                return inst.system_instruction, inst.rag_prompt_template
            synced_inst = await sync_ai_instructions_to_database(session)
            return synced_inst.system_instruction, synced_inst.rag_prompt_template
    except Exception as e:
        logger.warning(f"[AI Engine] Error reading AI instruction from database: {e}. Falling back to rag_ai_instructions.json schema.")

    file_schema = load_rag_ai_instructions_schema()
    return file_schema.system_instruction, file_schema.rag_prompt_template


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
    """Fallback Provider Handler for Groq Cloud and OpenRouter."""
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
    First reads RAG prompt template and AI system instruction from the database.
    """
    return await evaluate_candidate_with_fallback(candidate_text, job_description, db=db)


async def evaluate_candidate_with_fallback(
    candidate_text: str,
    job_description: str,
    db: Optional[Any] = None,
) -> Tuple[CandidateEvaluationResult, str]:
    """
    Executes full candidate evaluation across the multi-provider cascade:
    1. Reads RAG prompt template and AI system instructions from the database prior to API calls.
    2. Builds RAG augmented prompt with database template.
    3. Multi-provider cascade: Gemini -> Groq -> Mistral -> OpenRouter.
    """
    # 1. Read RAG & AI instructions from database before API call
    system_instruction, rag_prompt_template = await get_active_ai_instruction(db)
    logger.info("[AI Evaluator] Loaded active RAG & AI instructions from database before API dispatch.")

    user_prompt = build_rag_augmented_prompt(
        candidate_text, job_description, rag_template=rag_prompt_template
    )

    # 2. Try Primary: Gemini
    try:
        gemini_result = await _call_gemini(user_prompt, system_instruction=system_instruction)
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
    for groq_model in ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.1-8b-instant", "llama3-70b-8192"]:
        try:
            raw_json = await _call_openai_compatible_provider(
                base_url="https://api.groq.com/openai/v1",
                api_key=settings.GROQ_API_KEY,
                model_name=groq_model,
                prompt=user_prompt,
                system_instruction=system_instruction,
            )
            cleaned_json = _clean_json_string(raw_json)
            validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
            return validated, f"groq/{groq_model}"
        except Exception as groq_err:
            if "model_not_found" in str(groq_err) or "404" in str(groq_err):
                logger.info(f"Groq {groq_model} not accessible, attempting fallback...")
                continue
            logger.warning(
                f"Secondary provider (Groq {groq_model}) failed/throttled: {groq_err}. Failing over to Mistral/OpenRouter...")
            break

    # 4. Try Mistral AI (Free Tier / Experiment Plan: mistral-small-latest, open-mistral-nemo, open-mistral-7b)
    if settings.MISTRAL_API_KEY and settings.MISTRAL_API_KEY.strip():
        for mistral_model in ["mistral-small-latest", "open-mistral-nemo", "open-mistral-7b"]:
            try:
                raw_json = await _call_openai_compatible_provider(
                    base_url="https://api.mistral.ai/v1",
                    api_key=settings.MISTRAL_API_KEY,
                    model_name=mistral_model,
                    prompt=user_prompt,
                    system_instruction=system_instruction,
                )
                cleaned_json = _clean_json_string(raw_json)
                validated = CandidateEvaluationResult.model_validate_json(cleaned_json)
                return validated, f"mistral/{mistral_model}"
            except Exception as mistral_err:
                logger.warning(
                    f"Mistral AI model {mistral_model} failed/throttled: {mistral_err}. Continuing cascade..."
                )
                continue

    # 5. Try Quaternary: OpenRouter Free Models Pool Fallback
    for or_model in ["meta-llama/llama-3.1-8b-instruct:free", "meta-llama/llama-3.1-8b-instruct", "meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"]:
        try:
            raw_json = await _call_openai_compatible_provider(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
                model_name=or_model,
                prompt=user_prompt,
                system_instruction=system_instruction,
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
