import io
import logging
import re
import pypdf

logger = logging.getLogger("kayatix.pdf")


def extract_clean_pdf_text(file_bytes: bytes, max_chars: int = 18000) -> str:
    """
    Extracts text from standard resumes or LinkedIn 'Save to PDF' exports,
    stripping noise and normalizing whitespace to save LLM input tokens.
    """
    size_kb = len(file_bytes) / 1024
    logger.info(f"[PDF Extractor] Processing uploaded resume PDF ({size_kb:.1f} KB)...")
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for idx, page in enumerate(reader.pages):
            extracted = page.extract_text()
            if extracted:
                pages_text.append(extracted)
        raw_text = "\n".join(pages_text)
        logger.info(f"[PDF Extractor] Extracted raw text across {len(reader.pages)} page(s) ({len(raw_text)} chars).")
    except Exception as e:
        logger.error(f"[PDF Extractor] Failed to parse PDF: {e}")
        raise ValueError(f"Corrupted or unreadable PDF file: {str(e)}")

    # Normalize excessive spaces and line breaks
    cleaned = re.sub(r"[ \t]+", " ", raw_text)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned).strip()

    if len(cleaned) < 40:
        logger.warning(f"[PDF Extractor] PDF selectable text is too short ({len(cleaned)} chars). Likely a scanned image.")
        raise ValueError("PDF appears to be a scanned image without selectable text.")

    logger.info(f"[PDF Extractor] Cleaned resume text ready for AI evaluation ({len(cleaned[:max_chars])} chars).")
    return cleaned[:max_chars]
