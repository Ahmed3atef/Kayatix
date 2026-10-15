import httpx
import trafilatura


async def scrape_candidate_portfolio(url: str, max_chars: int = 15000) -> str:
    """
    Legally fetches and cleans a candidate's public portfolio, blog, or GitHub profile page.
    Removes HTML boilerplate, navbars, and scripts using Trafilatura.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HRCopilotBot/1.0; +http://localhost)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise ValueError(f"Website returned HTTP {response.status_code}")
        html_content = response.text

    # Extract main readable content and preserve markdown formatting
    extracted_text = trafilatura.extract(
        html_content,
        include_links=True,
        include_images=False,
        include_tables=True,
        output_format="txt",
    )

    if not extracted_text or len(extracted_text.strip()) < 50:
        raise ValueError("Could not extract sufficient readable text from the website.")

    return extracted_text.strip()[:max_chars]
