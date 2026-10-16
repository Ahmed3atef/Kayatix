import asyncio
import base64
import logging
import re
from typing import Optional, Tuple
import httpx
from google import genai
from google.genai import types
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


async def extract_text_with_gemini_vision(
    file_bytes: bytes,
    api_key: Optional[str] = None,
    max_chars: int = 24000,
    model: str = "gemini-2.5-flash-lite",
) -> str:
    """
    Tier 1 Cloud OCR: Uses Gemini 2.5 Flash-Lite native multimodal PDF vision
    to extract structured Markdown from scanned, Arabic/English, or multi-column PDFs.
    """
    clean_key = (api_key or settings.GEMINI_API_KEY or "").strip()
    if not clean_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    size_kb = len(file_bytes) / 1024
    logger.info(f"[Gemini Vision OCR] Processing PDF in cloud ({size_kb:.1f} KB, Model: '{model}')...")

    client = genai.Client(api_key=clean_key)
    ocr_prompt = (
        "You are a high-precision OCR and document layout parser. "
        "Extract all text from this PDF resume into clean, well-structured Markdown. "
        "Preserve all headings, bullet points, tables, dates, links, and contact details. "
        "Maintain the original language (Arabic and/or English) accurately without translating or summarizing. "
        "Return ONLY the extracted Markdown content."
    )

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
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

    logger.info(f"[Gemini Vision OCR] Extracted {len(cleaned)} chars of Markdown.")
    return cleaned


async def extract_text_with_mistral_ocr(
    file_bytes: bytes,
    api_key: Optional[str] = None,
    max_chars: int = 24000,
    model: str = "mistral-ocr-latest",
    max_retries: int = 2,
    initial_backoff: float = 1.0,
) -> str:
    """
    Tier 2 Cloud OCR: Extracts structured Markdown using Mistral AI OCR REST API.
    """
    clean_key = (api_key or settings.MISTRAL_API_KEY or "").strip()
    if not clean_key:
        raise ValueError("MISTRAL_API_KEY is not configured.")

    b64_pdf = encode_pdf_to_base64(file_bytes)
    data_url = f"data:application/pdf;base64,{b64_pdf}"

    payload = {
        "model": model,
        "document": {
            "type": "document_url",
            "document_url": data_url,
        },
        "include_image_base64": False,
    }

    backoff = initial_backoff
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                resp = await http_client.post(
                    "https://api.mistral.ai/v1/ocr",
                    headers={
                        "Authorization": f"Bearer {clean_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code in (401, 402, 403):
                    raise ValueError(f"Mistral API auth/quota error (HTTP {resp.status_code}): {resp.text}")
                if resp.status_code == 429:
                    raise RuntimeError("Mistral API rate limit reached (HTTP 429)")
                if resp.status_code != 200:
                    raise RuntimeError(f"Mistral OCR error (HTTP {resp.status_code}): {resp.text}")

                data = resp.json()
                pages = data.get("pages", [])
                pages_output = [
                    f"## Page {p.get('index', 0) + 1}\n\n{(p.get('markdown') or '').strip()}"
                    for p in pages
                    if (p.get("markdown") or "").strip()
                ]
                combined_md = "\n\n".join(pages_output)
                cleaned = _clean_markdown(combined_md, max_chars)

                logger.info(f"[Mistral OCR] Extracted {len(cleaned)} chars across {len(pages)} page(s).")
                return cleaned

        except ValueError as auth_err:
            raise auth_err
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 2

    raise RuntimeError(f"Mistral OCR failed after {max_retries} attempts: {last_err}")


async def extract_text_with_llamaparse(
    file_bytes: bytes,
    api_key: Optional[str] = None,
    max_chars: int = 24000,
) -> str:
    """
    Tier 3 Cloud OCR: Uses LlamaCloud's LlamaParse REST API (Free 1,000 pages/day)
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
    mistral_api_key: Optional[str] = None,
    llama_api_key: Optional[str] = None,
    max_chars: int = 24000,
) -> Tuple[str, str]:
    """
    Master Zero-Local-Parser Cloud OCR Pipeline.
    Order of execution:
    1. Gemini 2.5 Flash-Lite Native Vision (Free 30 RPM / 1,500 RPD)
    2. Mistral AI OCR (if valid MISTRAL_API_KEY is present)
    3. LlamaParse Cloud API (Free 1,000 pages/day)
    Returns: Tuple[extracted_markdown, provider_used]
    """
    # 1. Gemini Vision OCR
    try:
        text = await extract_text_with_gemini_vision(file_bytes, api_key=gemini_api_key, max_chars=max_chars)
        if len(text) >= 40:
            return text, "gemini_vision_ocr"
    except Exception as e:
        logger.warning(f"[PDF Pipeline] Gemini Vision OCR failed/skipped: {e}")

    # 2. Mistral AI OCR
    try:
        text = await extract_text_with_mistral_ocr(file_bytes, api_key=mistral_api_key, max_chars=max_chars)
        if len(text) >= 40:
            return text, "mistral_ocr"
    except Exception as e:
        logger.warning(f"[PDF Pipeline] Mistral OCR failed/skipped: {e}")

    # 3. LlamaParse Cloud
    try:
        text = await extract_text_with_llamaparse(file_bytes, api_key=llama_api_key, max_chars=max_chars)
        if len(text) >= 40:
            return text, "llamaparse_cloud"
    except Exception as e:
        logger.error(f"[PDF Pipeline] LlamaParse Cloud failed/skipped: {e}")

    raise RuntimeError(
        "All cloud PDF OCR providers failed or hit rate limits. "
        "Ensure GEMINI_API_KEY, MISTRAL_API_KEY, or LLAMA_CLOUD_API_KEY is configured."
    )

    raise RuntimeError(
        "All cloud PDF OCR providers failed or hit rate limits. "
        "Ensure GEMINI_API_KEY, MISTRAL_API_KEY, or LLAMA_CLOUD_API_KEY is configured."
    )

