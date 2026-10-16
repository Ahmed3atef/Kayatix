import asyncio
import json
import logging
import re
from typing import List, Optional, Tuple
from google import genai
from google.genai import types
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from app.core.config import settings
from app.services.pdf_service import extract_pdf_content

logger = logging.getLogger("kayatix.evaluator")


class InterviewQuestion(BaseModel):
    category: str = Field(description="Technical, Behavioral, or Resume-Gap")
    question: str
    target_skill_or_gap: str = Field(default="", description="The exact skill or resume claim being tested")
    expected_answer_criteria: str


class HRAnalysisResult(BaseModel):
    candidate_name: Optional[str] = None
    match_percentage: int = Field(ge=0, le=100)
    matched_skills: List[str] = Field(default_factory=list)
    missing_critical_skills: List[str] = Field(default_factory=list)
    years_of_experience: float = Field(default=0.0)
    executive_summary: str = Field(default="")
    red_flags: List[str] = Field(default_factory=list)
    tailored_interview_questions: List[InterviewQuestion] = Field(default_factory=list)

    @property
    def estimated_years_experience(self) -> float:
        return self.years_of_experience

    @property
    def red_flags_and_gaps(self) -> List[str]:
        return self.red_flags

    def to_candidate_evaluation_result(self):
        from app.schemas.payloads import CandidateEvaluationResult, InterviewQuestionSchema
        return CandidateEvaluationResult(
            candidate_name=self.candidate_name or "Unknown Candidate",
            match_percentage=self.match_percentage,
            executive_summary=self.executive_summary,
            estimated_years_experience=self.years_of_experience,
            matched_skills=self.matched_skills or [],
            missing_critical_skills=self.missing_critical_skills or [],
            detected_projects_and_impact=[],
            red_flags_and_gaps=self.red_flags or [],
            tailored_interview_questions=[
                InterviewQuestionSchema(
                    category=q.category,
                    question=q.question,
                    target_area=q.target_skill_or_gap,
                    expected_answer_criteria=q.expected_answer_criteria,
                )
                for q in self.tailored_interview_questions
            ],
        )


SYSTEM_INSTRUCTION = (
    "You are an unbiased Senior Technical HR Specialist powered by the Kayatix (A.Y.A.T.) Engine. "
    "Evaluate the candidate's resume and portfolio (in Arabic or English) against the Job Description "
    "strictly based on verifiable skills, project complexity, and measurable impact. "
    "Output strict JSON conforming to the requested schema."
)


def _clean_json(raw: str) -> str:
    cleaned = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    return cleaned


async def evaluate_candidate_pipeline(
    pdf_bytes: bytes,
    job_description: str,
    portfolio_markdown: str = "",
    gemini_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    ollama_api_key: Optional[str] = None,
    ollama_base_url: Optional[str] = None,
    llama_api_key: Optional[str] = None,
) -> Tuple[HRAnalysisResult, str]:
    """
    1. Attempts Single-Shot Native PDF Multimodal Evaluation on Gemini Flash (1 API call total).
    2. On rate-limit/failure, runs Cloud OCR (Gemini Vision / LlamaParse / pypdf)
       and evaluates the resulting Markdown on Groq (Llama 3.3 70B) or Ollama Cloud Models.
    Returns: Tuple[HRAnalysisResult, pipeline_used]
    """
    gemini_key = (gemini_api_key or settings.GEMINI_API_KEY or "").strip()
    groq_key = (groq_api_key or settings.GROQ_API_KEY or "").strip()
    ollama_key = (ollama_api_key or settings.OLLAMA_API_KEY or "").strip()
    ollama_url = (ollama_base_url or settings.OLLAMA_BASE_URL or "https://ollama.com/v1").rstrip("/")
    llama_key = (llama_api_key or settings.LLAMA_CLOUD_API_KEY or "").strip()

    # PATH A: Single-Shot Native PDF Vision Evaluation via modern Gemini Flash models
    if gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            preferred_models = [
                "gemini-flash-lite-latest",
                "gemini-3.5-flash-lite",
                "gemini-3.8-flash",
                "gemini-flash-latest",
            ]
            prompt = f"""
            Evaluate the attached PDF Resume against the following Job Description.
            Additional Candidate Portfolio Data:
            {portfolio_markdown[:8000] if portfolio_markdown else "None provided."}

            === JOB DESCRIPTION ===
            {job_description}
            """

            for model_name in preferred_models:
                try:
                    logger.info(f"[AI Router] Attempting Single-Shot PDF Evaluation via Gemini model '{model_name}'...")
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                            prompt,
                        ],
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            response_mime_type="application/json",
                            response_schema=HRAnalysisResult,
                            temperature=0.1,
                        ),
                    )
                    if response and response.text:
                        result = HRAnalysisResult.model_validate_json(response.text)
                        return result, f"{model_name}-single-shot"
                except Exception as e:
                    err_msg = str(e)
                    logger.warning(f"[AI Router] Gemini single-shot failed on '{model_name}': {err_msg}")
                    # If 404 (model deprecated for this key) or 503 (service unavailable), failover to next model
                    if "404" in err_msg or "not_found" in err_msg.lower() or "503" in err_msg or "unavailable" in err_msg.lower():
                        continue
                    # If 429 (rate limit quota hit), stop hammering Gemini and fall back to PATH B
                    if "429" in err_msg or "quota" in err_msg.lower():
                        logger.warning("[AI Router] Gemini rate limit hit (429). Falling back to Cloud OCR / pypdf + Text LLM...")
                        break
        except Exception as client_err:
            logger.warning(f"[AI Router] Gemini single-shot initialization or call failed: {client_err}. Falling back to PATH B...")

    # PATH B: Extraction (Gemini Vision -> LlamaParse -> Local pypdf) -> Groq / Ollama Text Evaluation
    resume_md, ocr_provider = await extract_pdf_content(
        pdf_bytes,
        gemini_api_key=gemini_key or None,
        llama_api_key=llama_key or None,
    )

    schema_json = json.dumps(HRAnalysisResult.model_json_schema(), indent=2)
    text_prompt = f"""
    {SYSTEM_INSTRUCTION}

    Required JSON Schema:
    {schema_json}

    === JOB DESCRIPTION ===
    {job_description}

    === CANDIDATE RESUME (MARKDOWN) ===
    {resume_md}

    === CANDIDATE PORTFOLIO ===
    {portfolio_markdown[:6000] if portfolio_markdown else "None"}
    """

    # Try Groq (Llama 3.3 / Llama 3.1 / GPT-OSS / Qwen)
    if groq_key:
        groq_client = AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key,
        )
        groq_models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "llama3-70b-8192",
        ]
        for g_model in groq_models:
            try:
                resp = await groq_client.chat.completions.create(
                    model=g_model,
                    messages=[{"role": "user", "content": text_prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                raw_json = resp.choices[0].message.content or "{}"
                cleaned_json = _clean_json(raw_json)
                tag = "groq-llama-3.3-70b" if "llama-3.3" in g_model else f"groq-{g_model}"
                return HRAnalysisResult.model_validate_json(cleaned_json), f"{ocr_provider}+{tag}"
            except Exception as e:
                err_msg = str(e)
                if "404" in err_msg or "model_not_found" in err_msg.lower() or "not exist" in err_msg.lower():
                    logger.info(f"[AI Router] Groq model '{g_model}' not accessible, trying next Groq model...")
                    continue
                logger.warning(f"[AI Router] Groq evaluation on '{g_model}' failed: {e}")
                break

    # Try Ollama Cloud Models Fallback
    if ollama_key:
        ollama_client = AsyncOpenAI(
            base_url=ollama_url,
            api_key=ollama_key,
        )
        ollama_models = [
            "gpt-oss:120b",
            "gpt-oss:20b",
            "gemma4:31b",
            "nemotron-3-nano:30b",
            "nemotron-3-super",
            "nemotron-3-ultra",
            "beam",
        ]
        for o_model in ollama_models:
            try:
                resp = await ollama_client.chat.completions.create(
                    model=o_model,
                    messages=[{"role": "user", "content": text_prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                raw_json = resp.choices[0].message.content or "{}"
                cleaned_json = _clean_json(raw_json)
                return HRAnalysisResult.model_validate_json(cleaned_json), f"{ocr_provider}+ollama-{o_model}"
            except Exception as e:
                logger.warning(f"[AI Router] Ollama model '{o_model}' failed: {e}")
                continue

    raise RuntimeError("All evaluation providers failed or hit rate limits.")

