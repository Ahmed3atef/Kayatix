import json
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import httpx
import trafilatura

logger = logging.getLogger("kayatix.scraper")


def extract_strings_from_json(obj) -> list[str]:
    """Recursively extracts human-readable text strings from nested JSON data."""
    strings = []
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) >= 3 and not s.startswith("http") and not s.startswith("data:"):
            strings.append(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings.extend(extract_strings_from_json(v))
    elif isinstance(obj, list):
        for item in obj:
            strings.extend(extract_strings_from_json(item))
    return strings


def extract_strings_from_js(js_content: str) -> list[str]:
    """Extracts human-readable candidate strings, titles, and skills from bundled JavaScript."""
    raw_strings = re.findall(r"\"([^\"]{3,400})\"|\x27([^\x27]{3,400})\x27|`([^`]{3,400})`", js_content)
    cleaned = []
    seen = set()
    for group in raw_strings:
        s = next((g for g in group if g), "").strip()
        if not s or s in seen or len(s) < 3:
            continue
        if any(s.startswith(p) for p in (
            "./", "../", "http://", "https://", "application/", "text/", "image/",
            "data:", "rgba(", "var(--", "px", "#", "width:", "height:", "display:"
        )):
            continue
        if re.match(r"^[a-zA-Z0-9_\-\.\/]+$", s) and " " not in s and len(s) > 20:
            continue
        # Keep strings that have spaces (sentences/phrases) or start with a capital letter (names/skills)
        if " " in s or s[0].isupper() or len(s) > 8:
            seen.add(s)
            cleaned.append(s)
    return cleaned


class TextExtractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.meta_parts = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v for k, v in attrs if k and v}

        # Extract rich meta tags (description, og:description, keywords, author, title)
        if tag == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content", "").strip()
            if content and (
                name in ("description", "keywords", "author", "title")
                or prop in ("og:description", "og:title", "twitter:description", "twitter:title")
            ):
                if content not in self.meta_parts:
                    self.meta_parts.append(content)

        # Extract image alt text
        if tag == "img":
            alt = attrs_dict.get("alt", "").strip()
            if alt and len(alt) > 3 and alt not in self.parts:
                self.parts.append(alt)

        # Handle scripts: keep JSON-LD structured data, skip raw js/css
        if tag in ("script", "style", "svg"):
            type_attr = attrs_dict.get("type", "").lower()
            if tag == "script" and "ld+json" in type_attr:
                self.skip = False
            else:
                self.skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg"):
            self.skip = False

    def handle_data(self, data):
        if not self.skip and data.strip():
            clean = data.strip()
            if len(clean) > 1 and clean not in self.parts:
                self.parts.append(clean)

    def get_extracted_text(self) -> str:
        all_pieces = []
        for m in self.meta_parts:
            if m and m not in all_pieces:
                all_pieces.append(m)
        for p in self.parts:
            if p and p not in all_pieces:
                all_pieces.append(p)
        return "\n".join(all_pieces).strip()


async def try_extract_github_profile(url: str, client: httpx.AsyncClient) -> str:
    """Extracts public developer details, bio, and repositories from GitHub API."""
    parsed = urlparse(url)
    if "github.com" not in parsed.netloc.lower():
        return ""
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not path_parts:
        return ""
    username = path_parts[0]
    if username in ("features", "pricing", "explore", "topics", "collections", "trending", "login", "signup", "about"):
        return ""

    headers = {
        "User-Agent": "Kayatix-Candidate-Screener/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    lines = [f"GitHub Profile: https://github.com/{username}"]
    try:
        r_user = await client.get(f"https://api.github.com/users/{username}", headers=headers, timeout=5.0)
        if r_user.status_code == 200:
            u_data = r_user.json()
            if u_data.get("name"):
                lines.append(f"Candidate Name: {u_data['name']}")
            if u_data.get("bio"):
                lines.append(f"Bio: {u_data['bio']}")
            if u_data.get("company"):
                lines.append(f"Company: {u_data['company']}")
            if u_data.get("location"):
                lines.append(f"Location: {u_data['location']}")
            if u_data.get("blog"):
                lines.append(f"Website/Blog: {u_data['blog']}")

        r_repos = await client.get(
            f"https://api.github.com/users/{username}/repos?sort=updated&per_page=8",
            headers=headers,
            timeout=5.0,
        )
        if r_repos.status_code == 200:
            repos_data = r_repos.json()
            if isinstance(repos_data, list) and repos_data:
                lines.append("Key Repositories & Tech Stack:")
                for repo in repos_data:
                    r_name = repo.get("name", "")
                    r_desc = repo.get("description") or "Open source repository"
                    r_lang = repo.get("language") or "Code"
                    lines.append(f" - {r_name} ({r_lang}): {r_desc}")
    except Exception:
        pass

    return "\n".join(lines) if len(lines) > 1 else ""


def format_dynamic_api_response(data) -> str:
    """Dynamically formats structured API response data (dict or list) into clean readable profile text."""
    lines = []
    if isinstance(data, dict):
        top_fields = []
        for k in ("name", "full_name", "candidate_name", "title", "headline", "role", "bio", "about", "summary", "description", "email", "location"):
            if k in data and isinstance(data[k], str) and data[k].strip():
                top_fields.append(f"{k.replace('_', ' ').title()}: {data[k].strip()}")
        if top_fields:
            lines.append("\n".join(top_fields))

        for k, v in data.items():
            if k.lower() in ("name", "full_name", "candidate_name", "title", "headline", "role", "bio", "about", "summary", "description", "email", "location"):
                continue
            if isinstance(v, list) and v:
                lines.append(f"\n{k.replace('_', ' ').title()}:")
                for item in v:
                    if isinstance(item, str):
                        lines.append(f"  - {item}")
                    elif isinstance(item, dict):
                        item_summary = []
                        for sub_k in ("title", "name", "role", "position", "company", "organization", "duration", "dates", "period", "degree", "school"):
                            if sub_k in item and item[sub_k]:
                                item_summary.append(str(item[sub_k]))
                        hdr = " - ".join(item_summary) or "Item"
                        desc = item.get("description") or item.get("desc") or item.get("bio") or ""
                        bullets = item.get("tasks") or item.get("responsibilities") or item.get("bullets") or item.get("skills") or item.get("items") or []
                        lines.append(f"  * {hdr}")
                        if desc:
                            lines.append(f"    {desc}")
                        if isinstance(bullets, list):
                            for b in bullets:
                                lines.append(f"      - {b}")
            elif isinstance(v, str) and len(v.strip()) > 3:
                lines.append(f"{k.replace('_', ' ').title()}: {v.strip()}")

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                lines.append(f"- {item}")
            elif isinstance(item, dict):
                item_summary = []
                for sub_k in ("title", "name", "role", "position", "company", "organization", "duration", "dates", "period", "degree", "school"):
                    if sub_k in item and item[sub_k]:
                        item_summary.append(str(item[sub_k]))
                hdr = " - ".join(item_summary) or "Item"
                desc = item.get("description") or item.get("desc") or item.get("bio") or ""
                bullets = item.get("tasks") or item.get("responsibilities") or item.get("bullets") or item.get("skills") or item.get("items") or []
                lines.append(f"* {hdr}")
                if desc:
                    lines.append(f"  {desc}")
                if isinstance(bullets, list):
                    for b in bullets:
                        lines.append(f"    - {b}")

    return "\n".join(lines).strip()


def discover_dynamic_endpoints_from_code(
    code_corpus: list[str], base_url: str
) -> tuple[set[str], list[str], set[str]]:
    """
    Dynamically discovers backend API hosts, REST endpoints, JSON files, and route paths
    by searching across the HTML and JavaScript source code of the website with zero hardcoding.
    Returns (api_bases, sorted_endpoints, full_urls).
    """
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    api_bases: set[str] = {origin, f"{origin}/api"}
    relative_endpoints: set[str] = set()
    full_urls: set[str] = set()
    high_priority_endpoints: set[str] = set()

    media_extensions = (
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
        ".css", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webm",
        ".mp3", ".wav", ".map", ".min.js"
    )
    ignored_prefixes = (
        "//", "/*", "*/", "/div", "/span", "/p", "/h1", "/h2", "/h3",
        "/a", "/button", "/form", "/input", "/head", "/body", "/html"
    )

    for code in code_corpus:
        if not code:
            continue

        # 1. API Bases from code (PaaS and custom API domains)
        for m in re.finditer(
            r"https?://[a-zA-Z0-9_\-\.]+(?::\d+)?(?:/[a-zA-Z0-9_\-]+)*(?:api|backend|v[0-9]|service)[a-zA-Z0-9_\-\/]*",
            code,
            re.I,
        ):
            api_bases.add(m.group(0).rstrip("/"))

        for m in re.finditer(
            r"https?://[a-zA-Z0-9_\-\.]+(?:koyeb\.app|railway\.app|render\.com|onrender\.com|fly\.dev|herokuapp\.com|supabase\.co|firebaseio\.com|vercel\.app|netlify\.app)[a-zA-Z0-9_\-\/]*",
            code,
            re.I,
        ):
            api_bases.add(m.group(0).rstrip("/"))

        for m in re.finditer(
            r"(?:API_URL|BASE_URL|BACKEND_URL|SERVER_URL|API_BASE|baseURL|apiUrl|apiEndpoint|NEXT_PUBLIC_API_URL|VITE_API_URL|REACT_APP_API_URL)\s*[:=]\s*[\x22\x27\x60](https?://[^\x22\x27\x60\s]+)[\x22\x27\x60]",
            code,
            re.I,
        ):
            api_bases.add(m.group(1).rstrip("/"))

        # 2. Network calls & HTTP client invocations in code (highest priority)
        for m in re.finditer(
            r"(?:fetch|axios(?:\.\w+)?|http(?:\.\w+)?|api(?:\.\w+)?|\.get|\.post|\.request)\s*\(\s*[\x22\x27\x60]([^\x22\x27\x60\s\?\#\)]+)",
            code,
            re.I,
        ):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://")):
                full_urls.add(target)
            elif target.startswith("/"):
                relative_endpoints.add(target)
                high_priority_endpoints.add(target)

        # 3. Object properties (url, path, endpoint, route, href, uri)
        for m in re.finditer(
            r"(?:url|endpoint|route|path|href|uri)\s*[:=]\s*[\x22\x27\x60](/[^\x22\x27\x60\s\?\#\)]+)[\x22\x27\x60]",
            code,
            re.I,
        ):
            target = m.group(1).strip()
            relative_endpoints.add(target)
            high_priority_endpoints.add(target)

        # 4. JSON data files referenced anywhere in code
        for m in re.finditer(r"[\x22\x27\x60](/[a-zA-Z0-9_\-\./]+\.json)[\x22\x27\x60]", code, re.I):
            target = m.group(1).strip()
            relative_endpoints.add(target)
            high_priority_endpoints.add(target)

        # 5. String concatenation with Base/API variables (e.g. API_URL + '/profile-data/')
        for m in re.finditer(
            r"(?:BASE|URL|API|HOST|CLIENT|ORIGIN|SERVER)\s*\+\s*[\x22\x27\x60](/[^\x22\x27\x60\s\?\#\)]+)[\x22\x27\x60]",
            code,
            re.I,
        ):
            relative_endpoints.add(m.group(1).strip())

        # 6. Template literals with leading slash
        for m in re.finditer(r"\x60(/[a-zA-Z0-9_\-\./]+)\x60", code):
            relative_endpoints.add(m.group(1).strip())

        # 7. Quoted route and endpoint paths in code
        for m in re.finditer(r"[\x22\x27\x60](/(?:[a-zA-Z0-9_\-]+/)*[a-zA-Z0-9_\-]+/?)[\x22\x27\x60]", code):
            relative_endpoints.add(m.group(1).strip())

    # Filter out static media assets, invalid characters, or HTML tags
    clean_endpoints = set()
    for ep in relative_endpoints:
        ep_low = ep.lower()
        if ep_low.endswith(media_extensions):
            continue
        if any(ep_low.startswith(p) for p in ignored_prefixes):
            continue
        if not (2 <= len(ep) <= 100):
            continue
        clean_endpoints.add(ep)

    # Sort endpoints by relevance score
    def score_ep(ep: str) -> int:
        score = 0
        if ep in high_priority_endpoints:
            score += 100
        if ep.lower().endswith(".json"):
            score += 80
        ep_l = ep.lower()
        if any(kw in ep_l for kw in ("profile", "skill", "experience", "project", "about", "resume", "bio", "work", "cv", "user", "data", "api")):
            score += 50
        if "/" in ep.strip("/"):
            score += 10
        return score

    sorted_endpoints = sorted(clean_endpoints, key=score_ep, reverse=True)
    return api_bases, sorted_endpoints, full_urls


async def try_extract_spa_api_data(
    url: str, code_corpus: list[str], client: httpx.AsyncClient
) -> list[str]:
    """
    Discovers dynamic backend REST API endpoints and data files by scanning the website code
    (HTML + JavaScript) with regular expressions and fetches candidate data.
    """
    api_bases, endpoints, full_urls = discover_dynamic_endpoints_from_code(code_corpus, url)

    targets: list[str] = list(full_urls)
    for base in api_bases:
        for ep in endpoints[:20]:
            if base.endswith("/api") and ep.startswith("/api/"):
                clean_ep = ep[4:]
            else:
                clean_ep = ep
            target = base.rstrip("/") + "/" + clean_ep.lstrip("/")
            if target not in targets:
                targets.append(target)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    collected = []
    # Test up to 15 prioritized targets
    for target in targets[:15]:
        try:
            r = await client.get(target, headers=headers, timeout=4.0)
            if r.status_code == 200:
                # 1. Try JSON parsing
                try:
                    data = r.json()
                    formatted = format_dynamic_api_response(data)
                    if formatted and len(formatted) > 15:
                        collected.append(formatted)
                        continue
                except Exception:
                    pass

                # 2. Plain text / markdown fallback
                text = r.text.strip()
                if 30 <= len(text) <= 15000 and not text.startswith("<!DOCTYPE") and "<html" not in text.lower():
                    collected.append(text)
        except Exception:
            continue

    return collected


async def try_extract_from_spa_bundles(url: str, html_content: str, client: httpx.AsyncClient) -> list[str]:
    """Fetches and extracts candidate text from referenced SPA JavaScript bundles and dynamic APIs."""
    scripts = re.findall(r"""<script[^>]+src=["\x27]([^"\x27]+)["\x27]""", html_content, re.IGNORECASE)
    preloads = re.findall(
        r"""<link[^>]+(?:rel=["\x27]modulepreload["\x27]|as=["\x27]script["\x27])[^>]+href=["\x27]([^"\x27]+)["\x27]""",
        html_content,
        re.IGNORECASE,
    )
    all_scripts = scripts + preloads

    candidate_scripts = []
    for s in all_scripts:
        s_lower = s.lower()
        if any(ign in s_lower for ign in ("google", "analytics", "gtm", "sentry", "clarity", "hotjar", "facebook", "segment", "polyfill")):
            continue
        if s.endswith(".js") or "/js/" in s or "/assets/" in s or "/_next/" in s or "/static/" in s:
            full_url = urljoin(url, s)
            if full_url not in candidate_scripts:
                candidate_scripts.append(full_url)

    extracted_strings = []
    js_contents = []

    # Extract inline scripts from HTML
    inline_scripts = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html_content, re.DOTALL | re.IGNORECASE)
    for inline in inline_scripts:
        inline_clean = inline.strip()
        if len(inline_clean) > 10 and not any(ign in inline_clean.lower() for ign in ("googletagmanager", "google-analytics")):
            js_contents.append(inline_clean)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    for s_url in candidate_scripts[:5]:
        try:
            resp = await client.get(s_url, headers=headers, timeout=6.0)
            if resp.status_code == 200 and resp.text:
                js_contents.append(resp.text)
                strings = extract_strings_from_js(resp.text)
                extracted_strings.extend(strings)
        except Exception:
            continue

    # Dynamically search website code (HTML + bundled JS) for API endpoints and fetch data
    code_corpus = [html_content] + js_contents
    api_data = await try_extract_spa_api_data(url, code_corpus, client)
    if api_data:
        extracted_strings = api_data + extracted_strings

    return extracted_strings


async def scrape_candidate_portfolio(url: str, max_chars: int = 15000) -> str:
    """
    Legally fetches and cleans a candidate's public portfolio, blog, or GitHub profile page.
    Fully supports Single-Page Applications (SPAs) by extracting from HTML, Next.js __NEXT_DATA__,
    OpenGraph meta tags, client-side JavaScript bundle strings, and dynamically discovered backend APIs.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    logger.info(f"[Portfolio Scraper] Starting portfolio extraction for URL: {url}")
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            # 1. Specialized extraction for GitHub profiles
            if "github.com" in url.lower():
                logger.info(f"[Portfolio Scraper] Detected GitHub profile URL: {url}")
                gh_text = await try_extract_github_profile(url, client)
                if gh_text and len(gh_text) >= 40:
                    logger.info(f"[Portfolio Scraper] Successfully extracted GitHub profile ({len(gh_text)} chars).")
                    return gh_text[:max_chars]

            # 2. Standard web fetch
            response = await client.get(url, headers=headers)
            logger.info(f"[Portfolio Scraper] HTTP response {response.status_code} ({len(response.text)} bytes).")
            if response.status_code == 403:
                if "linkedin.com" in url.lower():
                    raise ValueError(
                        "LinkedIn profiles require user login and block web scrapers (HTTP 403). "
                        "Please use our Legal LinkedIn Sourcing (X-Ray) page or export the LinkedIn profile as PDF to screen it."
                    )
                raise ValueError(
                    f"Website returned HTTP 403 (Access Denied). "
                    "The target website is blocking automated scraping. You can paste the candidate's bio or portfolio text directly below."
                )
            if response.status_code == 404:
                raise ValueError("Website returned HTTP 404 (Not Found). Please check the portfolio URL.")
            if response.status_code != 200:
                raise ValueError(f"Website returned HTTP {response.status_code}")
            html_content = response.text

            # 3. Trafilatura main body extraction
            t_text = (trafilatura.extract(
                html_content,
                include_links=True,
                include_images=False,
                include_tables=True,
                output_format="txt",
            ) or "").strip()

            # 4. Meta tags, OpenGraph, and title extraction
            parser = TextExtractParser()
            try:
                parser.feed(html_content)
                p_text = parser.get_extracted_text()
            except Exception:
                p_text = ""

            # 5. Extract Next.js __NEXT_DATA__ or JSON-LD
            json_parts = []
            next_data_match = re.search(
                r'<script[^>]+id=["\x27]__NEXT_DATA__["\x27][^>]*>(.*?)</script>',
                html_content,
                re.DOTALL | re.IGNORECASE,
            )
            if next_data_match:
                try:
                    parsed_json = json.loads(next_data_match.group(1))
                    json_parts.extend(extract_strings_from_json(parsed_json))
                except Exception:
                    pass

            # 6. If total text is minimal (< 150 chars) or page has SPA indicators, extract from SPA JS bundles
            spa_strings = []
            current_len = len(t_text) + len(p_text) + sum(len(j) for j in json_parts)
            is_spa_shell = bool(
                re.search(r'id=["\x27](?:root|__next|app|__nuxt)["\x27]|<(?:router-outlet|app-root)\b', html_content, re.IGNORECASE)
            )
            if current_len < 150 or (is_spa_shell and current_len < 400):
                logger.info("[Portfolio Scraper] Page appears to be a client-side SPA. Inspecting JS bundles...")
                spa_strings = await try_extract_from_spa_bundles(url, html_content, client)

    except httpx.TimeoutException:
        logger.warning(f"[Portfolio Scraper] Request to {url} timed out.")
        raise ValueError("Website connection timed out after 12 seconds.")
    except httpx.RequestError as exc:
        logger.warning(f"[Portfolio Scraper] Network error connecting to {url}: {exc}")
        raise ValueError(f"Could not connect to website: {str(exc)}")

    # Combine all extracted sources
    combined = []
    if p_text:
        combined.append(p_text)
    if t_text and t_text not in p_text:
        combined.append(t_text)
    if json_parts:
        combined.append("\n".join(json_parts[:30]))
    if spa_strings:
        combined.append("\n".join(spa_strings[:50]))

    extracted_text = "\n\n".join(combined).strip()
    logger.info(
        f"[Portfolio Scraper] Combined extraction completed: {len(extracted_text)} chars "
        f"(Body: {len(t_text)}, Meta: {len(p_text)}, SPA items: {len(spa_strings)})."
    )

    if not extracted_text or len(extracted_text) < 30:
        logger.warning(f"[Portfolio Scraper] Insufficient text extracted (< 30 chars).")
        raise ValueError(
            "Could not extract sufficient readable text from the website (< 30 characters). "
            "The site may be a client-side JavaScript Single-Page App (SPA) or requires authentication. "
            "Tip: You can paste the candidate's bio or text directly into the fallback text box below."
        )

    return extracted_text[:max_chars]
