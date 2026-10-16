import asyncio
import base64
import io
import logging
import re
from typing import Optional, Tuple
import httpx
from google import genai
from google.genai import types
import pypdf
from app.core.config import settings

logger = logging.getLogger("kayatix.pdf")


def encode_pdf_to_base64(file_bytes: bytes) -> str:
    """Encodes PDF raw bytes into a UTF-8 base64 string for data URI payloads."""
    return base64.b64encode(file_bytes).decode("utf-8")


def _clean_markdown(raw_md: str, max_chars: int) -> str:
    """Normalizes whitespace while preserving Markdown headers, lists, and tables."""
    cleaned = re.sub(r"[ \t]+", " ", raw_md)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned).strip()
    return cleaned[:max_chars]


def extract_text_with_pypdf(file_bytes: bytes, max_chars: int = 18000) -> str:
    """
    Tier 3 Local CPU Fallback (Zero-Cost / Zero-Quota):
    Extracts text from selectable PDFs locally using pypdf.
    Consumes 0 cloud API quota and runs with zero latency.
    """
    if not file_bytes:
        raise ValueError("Empty PDF file bytes provided.")
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(f"## Page {idx + 1}\n\n{text.strip()}")
        combined = "\n\n".join(pages_text)
        cleaned = _clean_markdown(combined, max_chars)
        if len(cleaned) < 30:
            raise ValueError("PDF appears to be a scanned image without selectable text.")
        logger.info(f"[pypdf Local Fallback] Extracted {len(cleaned)} chars locally with zero quota usage.")
        return cleaned
    except ValueError as ve:
        raise ve
    except Exception as e:
        raise RuntimeError(f"pypdf extraction error: {e}")


async def extract_text_with_gemini_vision(
    file_bytes: bytes,
    api_key: Optional[str] = None,
    max_chars: int = 24000,
    model: Optional[str] = None,
) -> str:
    """
    Tier 1 Cloud Vision OCR: Uses modern Gemini Flash-Lite/Flash native multimodal PDF vision
    to extract structured Markdown from scanned, Arabic/English, or multi-column PDFs.
    Cascades across active models if a model is deprecated (404) or temporarily unavailable (503).
    """
    clean_key = (api_key or settings.GEMINI_API_KEY or "").strip()
    if not clean_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    size_kb = len(file_bytes) / 1024
    candidate_models = (
        [model]
        if model
        else [
            "gemini-3.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.8-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
            "gemini-1.5-flash",
        ]
    )

    client = genai.Client(api_key=clean_key)
    ocr_prompt = (
        "You are a high-precision OCR and document layout parser. "
        "Extract all text from this PDF resume into clean, well-structured Markdown. "
        "Preserve all headings, bullet points, tables, dates, links, and contact details. "
        "Maintain the original language (Arabic and/or English) accurately without translating or summarizing. "
        "Return ONLY the extracted Markdown content."
    )

    last_error: Optional[Exception] = None
    for model_name in candidate_models:
        try:
            logger.info(f"[Gemini Vision OCR] Processing PDF in cloud ({size_kb:.1f} KB, Model: '{model_name}')...")
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"),
                    ocr_prompt,
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )

            extracted_md = response.text or ""
            cleaned = _clean_markdown(extracted_md, max_chars)

            if len(cleaned) < 30:
                raise RuntimeError("Gemini Vision OCR returned insufficient text.")

            logger.info(f"[Gemini Vision OCR] Extracted {len(cleaned)} chars of Markdown using '{model_name}'.")
            return cleaned
        except Exception as e:
            err_msg = str(e)
            last_error = e
            if "insufficient text" in err_msg.lower():
                raise e
            logger.warning(f"[Gemini Vision OCR] Model '{model_name}' failed: {err_msg}")
            if "404" in err_msg or "not_found" in err_msg.lower() or "503" in err_msg or "unavailable" in err_msg.lower():
                continue
            if "429" in err_msg or "quota" in err_msg.lower():
                logger.warning("[Gemini Vision OCR] Gemini quota limit (429) hit. Stopping cascade.")
                break

    if last_error:
        raise last_error
    raise RuntimeError("Gemini Vision OCR returned insufficient text or no accessible models.")


async def extract_text_with_llamaparse(
    file_bytes: bytes,
    api_key: Optional[str] = None,
    max_chars: int = 24000,
) -> str:
    """
    Tier 2 Cloud OCR: Uses LlamaCloud's LlamaParse REST API (Free 1,000 pages/day)
    to convert complex/scanned PDFs into Markdown in the cloud.
    """
    clean_key = (api_key or settings.LLAMA_CLOUD_API_KEY or "").strip()
    if not clean_key:
        raise ValueError("LLAMA_CLOUD_API_KEY is not configured.")

    base_url = "https://api.cloud.llamaindex.ai/api/v1/parsing"
    headers = {"Authorization": f"Bearer {clean_key}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        files = {"file": ("resume.pdf", file_bytes, "application/pdf")}
        upload_resp = await client.post(f"{base_url}/upload", headers=headers, files=files)
        if upload_resp.status_code != 200:
            raise RuntimeError(f"LlamaParse upload failed: {upload_resp.text}")

        job_id = upload_resp.json().get("id")

        for _ in range(25):
            await asyncio.sleep(1.5)
            status_resp = await client.get(f"{base_url}/job/{job_id}", headers=headers)
            status = status_resp.json().get("status")
            if status == "SUCCESS":
                res_resp = await client.get(f"{base_url}/job/{job_id}/result/markdown", headers=headers)
                markdown_text = res_resp.json().get("markdown", "")
                cleaned = _clean_markdown(markdown_text, max_chars)
                logger.info(f"[LlamaParse Cloud] Extracted {len(cleaned)} chars of Markdown.")
                return cleaned
            elif status in ("ERROR", "CANCELED"):
                raise RuntimeError(f"LlamaParse job failed with status: {status}")

    raise TimeoutError("LlamaParse cloud extraction timed out.")


async def extract_pdf_content(
    file_bytes: bytes,
    gemini_api_key: Optional[str] = None,
    llama_api_key: Optional[str] = None,
    max_chars: int = 24000,
) -> Tuple[str, str]:
    """
    Master Quota-Protected PDF Extraction Pipeline.
    Order of execution:
    1. Gemini 2.5 Flash-Lite Native Vision (Free 30 RPM / 1,500 RPD)
    2. LlamaParse Cloud API (Free 1,000 pages/day, if key configured)
    3. pypdf Local CPU Parser (Zero-Cost / Zero-Quota fallback for selectable PDFs)
    Returns: Tuple[extracted_markdown, provider_used]
    """
    # 1. Gemini Vision OCR
    try:
        text = await extract_text_with_gemini_vision(file_bytes, api_key=gemini_api_key, max_chars=max_chars)
        if len(text) >= 40:
            return text, "gemini_vision_ocr"
    except Exception as e:
        logger.warning(f"[PDF Pipeline] Gemini Vision OCR failed/skipped: {e}")

    # 2. LlamaParse Cloud (if configured)
    llama_k = (llama_api_key or settings.LLAMA_CLOUD_API_KEY or "").strip()
    if llama_k:
        try:
            text = await extract_text_with_llamaparse(file_bytes, api_key=llama_k, max_chars=max_chars)
            if len(text) >= 40:
                return text, "llamaparse_cloud"
        except Exception as e:
            logger.warning(f"[PDF Pipeline] LlamaParse Cloud failed/skipped: {e}")

    # 3. Local pypdf CPU Parser (Zero-Cost / Zero-Quota Fallback)
    try:
        text = extract_text_with_pypdf(file_bytes, max_chars=max_chars)
        if len(text) >= 30:
            return text, "pypdf_local_parser"
    except Exception as e:
        logger.warning(f"[PDF Pipeline] Local pypdf fallback failed: {e}")

    raise RuntimeError(
        "All PDF extraction options failed. "
        "Cloud OCR options (Gemini / LlamaParse) failed or hit quota limits, "
        "and the document is a scanned image with no selectable text for local extraction."
    )
