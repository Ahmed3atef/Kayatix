"""
Services package: PDF parsing, web scraping, sourcing, and AI engine.
"""

from app.services.pdf_service import extract_clean_pdf_text
from app.services.scraper_service import scrape_candidate_portfolio
from app.services.sourcing_service import execute_linkedin_xray_search
from app.services.ai_engine import compute_request_hash, evaluate_candidate_with_fallback

__all__ = [
    "extract_clean_pdf_text",
    "scrape_candidate_portfolio",
    "execute_linkedin_xray_search",
    "compute_request_hash",
    "evaluate_candidate_with_fallback",
]
