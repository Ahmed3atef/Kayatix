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
    openrouter_api_key: Optional[str] = None,
    mistral_api_key: Optional[str] = None,
    llama_api_key: Optional[str] = None,
) -> Tuple[HRAnalysisResult, str]:
    """
    1. Attempts Single-Shot Native PDF Multimodal Evaluation on Gemini 2.5 Flash (1 API call total).
    2. On rate-limit/failure, runs Cloud OCR (Gemini Flash-Lite / Mistral / LlamaParse)
       and evaluates the resulting Markdown on Groq (Llama 3.3 70B) or OpenRouter.
    Returns: Tuple[HRAnalysisResult, pipeline_used]
    """
    gemini_key = (gemini_api_key or settings.GEMINI_API_KEY or "").strip()
    groq_key = (groq_api_key or settings.GROQ_API_KEY or "").strip()
    openrouter_key = (openrouter_api_key or settings.OPENROUTER_API_KEY or "").strip()
    mistral_key = (mistral_api_key or settings.MISTRAL_API_KEY or "").strip()
    llama_key = (llama_api_key or settings.LLAMA_CLOUD_API_KEY or "").strip()

    # PATH A: Single-Shot Native PDF Vision Evaluation via Gemini 2.5 Flash
    if gemini_key:
        try:
            logger.info("[AI Router] Attempting Single-Shot PDF Evaluation via Gemini 2.5 Flash...")
            client = genai.Client(api_key=gemini_key)
            prompt = f"""
            Evaluate the attached PDF Resume against the following Job Description.
            Additional Candidate Portfolio Data:
            {portfolio_markdown[:8000] if portfolio_markdown else "None provided."}

            === JOB DESCRIPTION ===
            {job_description}
            """
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
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
            result = HRAnalysisResult.model_validate_json(response.text)
            return result, "gemini-2.5-flash-single-shot"
        except Exception as e:
            logger.warning(f"[AI Router] Gemini 2.5 Flash single-shot failed ({e}). Falling back to Cloud OCR + Text LLM...")

    # PATH B: Cloud OCR Extraction -> Groq / OpenRouter Text Evaluation
    resume_md, ocr_provider = await extract_pdf_content(
        pdf_bytes,
        gemini_api_key=gemini_key or None,
        mistral_api_key=mistral_key or None,
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

    # Try Groq (Llama 3.3 70B)
    if groq_key:
        try:
            groq_client = AsyncOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key,
            )
            resp = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": text_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw_json = resp.choices[0].message.content or "{}"
            cleaned_json = _clean_json(raw_json)
            return HRAnalysisResult.model_validate_json(cleaned_json), f"{ocr_provider}+groq-llama-3.3-70b"
        except Exception as e:
            logger.warning(f"[AI Router] Groq evaluation failed: {e}")

    # Try OpenRouter Free Fallback
    if openrouter_key:
        try:
            or_client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_key,
            )
            resp = await or_client.chat.completions.create(
                model="meta-llama/llama-3.1-8b-instruct:free",
                messages=[{"role": "user", "content": text_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw_json = resp.choices[0].message.content or "{}"
            cleaned_json = _clean_json(raw_json)
            return HRAnalysisResult.model_validate_json(cleaned_json), f"{ocr_provider}+openrouter-free"
        except Exception as e:
            logger.error(f"[AI Router] OpenRouter evaluation failed: {e}")

    # Try Mistral AI Fallback
    if mistral_key:
        try:
            mistral_client = AsyncOpenAI(
                base_url="https://api.mistral.ai/v1",
                api_key=mistral_key,
            )
            resp = await mistral_client.chat.completions.create(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": text_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw_json = resp.choices[0].message.content or "{}"
            cleaned_json = _clean_json(raw_json)
            return HRAnalysisResult.model_validate_json(cleaned_json), f"{ocr_provider}+mistral-small"
        except Exception as e:
            logger.error(f"[AI Router] Mistral evaluation fallback failed: {e}")

    raise RuntimeError("All evaluation providers failed or hit rate limits.")

