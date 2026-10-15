import io
import re
import pypdf


def extract_clean_pdf_text(file_bytes: bytes, max_chars: int = 18000) -> str:
    """
    Extracts text from standard resumes or LinkedIn 'Save to PDF' exports,
    stripping noise and normalizing whitespace to save LLM input tokens.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                pages_text.append(extracted)
        raw_text = "\n".join(pages_text)
    except Exception as e:
        raise ValueError(f"Corrupted or unreadable PDF file: {str(e)}")

    # Normalize excessive spaces and line breaks
    cleaned = re.sub(r"[ \t]+", " ", raw_text)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned).strip()

    if len(cleaned) < 40:
        raise ValueError("PDF appears to be a scanned image without selectable text.")

    return cleaned[:max_chars]
