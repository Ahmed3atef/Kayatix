"""
Services package: Cloud PDF OCR, web scraping, sourcing, and AI engines.
"""

from app.services.pdf_service import (
    encode_pdf_to_base64,
    extract_pdf_content,
    extract_text_with_gemini_vision,
    extract_text_with_mistral_ocr,
    extract_text_with_llamaparse,
)
from app.services.ai_evaluator import (
    evaluate_candidate_pipeline,
    HRAnalysisResult,
    InterviewQuestion,
)
from app.services.scraper_service import scrape_candidate_portfolio
from app.services.sourcing_service import execute_linkedin_xray_search
from app.services.ai_engine import compute_request_hash, evaluate_candidate_with_fallback

__all__ = [
    "encode_pdf_to_base64",
    "extract_pdf_content",
    "extract_text_with_gemini_vision",
    "extract_text_with_mistral_ocr",
    "extract_text_with_llamaparse",
    "evaluate_candidate_pipeline",
    "HRAnalysisResult",
    "InterviewQuestion",
    "scrape_candidate_portfolio",
    "execute_linkedin_xray_search",
    "compute_request_hash",
    "evaluate_candidate_with_fallback",
]
