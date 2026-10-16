import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"


def _clean_title(filename: str, first_line: str) -> str:
    """Extracts a clean title from the markdown first H1 or filename."""
    if first_line.startswith("# "):
        return first_line.lstrip("# ").strip()
    name = Path(filename).stem
    # Strip leading digits like 01-, 02-
    clean_name = re.sub(r"^\d+[-_]", "", name)
    return clean_name.replace("-", " ").replace("_", " ").title()


def get_all_documentation_pages() -> List[Dict[str, Any]]:
    """
    Scans the local docs/ directory and returns metadata for all markdown pages in order.
    Enables users to add or edit markdown files locally and browse them dynamically.
    """
    if not DOCS_DIR.exists():
        return []

    pages = []
    # Sort files naturally by filename (01-..., 02-...)
    files = sorted([f for f in os.listdir(DOCS_DIR) if f.endswith(".md")])

    for idx, fname in enumerate(files):
        fpath = DOCS_DIR / fname
        slug = Path(fname).stem
        title = slug
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                title = _clean_title(fname, first_line)
        except Exception:
            title = slug.replace("-", " ").title()

        pages.append({
            "index": idx + 1,
            "slug": slug,
            "filename": fname,
            "title": title,
            "relative_path": f"docs/{fname}",
        })

    return pages


def get_documentation_page(slug: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the content, title, and pagination metadata for a specific documentation page.
    If slug is omitted or invalid, defaults to the first available documentation page.
    """
    pages = get_all_documentation_pages()
    if not pages:
        return None

    # Default to first page if none specified
    target_idx = 0
    if slug:
        for idx, p in enumerate(pages):
            if p["slug"] == slug or p["filename"] == slug or p["slug"].endswith(slug):
                target_idx = idx
                break

    active_page = pages[target_idx]
    fpath = DOCS_DIR / active_page["filename"]

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        content = f"# Error reading documentation\n\nCould not load file `{active_page['filename']}`: {e}"

    prev_page = pages[target_idx - 1] if target_idx > 0 else None
    next_page = pages[target_idx + 1] if target_idx < len(pages) - 1 else None

    return {
        "slug": active_page["slug"],
        "filename": active_page["filename"],
        "title": active_page["title"],
        "relative_path": active_page["relative_path"],
        "content": content,
        "all_pages": pages,
        "prev_page": prev_page,
        "next_page": next_page,
        "current_index": target_idx + 1,
        "total_pages": len(pages),
    }

