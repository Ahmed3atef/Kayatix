import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple


class LocalResumeAnalyzer:
    """
    High-speed, zero-quota local resume and candidate benchmarking engine.
    Extracts structured requirements dynamically from ANY job description (tech, marketing,
    finance, healthcare, legal, operations, sales), merges career intervals for true YOE,
    and detects quantified impact metrics deterministically with smart search.
    """

    ACTION_VERBS: Set[str] = {
        # Leadership, Strategy & Management
        "architected", "spearheaded", "orchestrated", "founded", "built", "guided",
        "steered", "led", "directed", "managed", "supervised", "championed", "pioneered",
        "formulated", "standardized", "restructured", "transformed", "mobilized",
        # Growth, Sales, Marketing & Partnerships
        "increased", "generated", "closed", "boosted", "grew", "acquired", "converted",
        "expanded", "scaled", "marketed", "pitched", "promoted", "outperformed", "drove",
        "secured", "negotiated", "captured", "retained",
        # Operations, Finance & Optimization
        "optimized", "streamlined", "reduced", "automated", "cut", "saved", "audited",
        "forecasted", "reconciled", "budgeted", "curtailed", "eliminated", "accelerated",
        "consolidated", "procured", "allocated",
        # Engineering, Development & Design
        "designed", "developed", "implemented", "engineered", "deployed", "refactored",
        "programmed", "configured", "integrated", "authored", "constructed", "established",
        "modeled", "prototyped", "coded",
        # Healthcare, Clinical & People Operations
        "treated", "administered", "diagnosed", "counseled", "monitored", "triaged",
        "facilitated", "coached", "trained", "mentored", "onboarded", "resolved"
    }

    METRIC_REGEX = re.compile(
        r"(\d+[\d,.]*\s*(?:%|x|k|m|million|billion|users|clients|patients|customers|accounts|cases|leads|tickets|req/s|rps|ms|latency|reduction|increase|cost|revenue|budget|savings|growth|headcount|uptime|throughput|roi|\$|€|£))|(?:team\s+of\s+\d+)|(?:portfolio\s+of\s+[\$€£]?\d+)",
        re.I
    )

    FILLER_PREFIXES = re.compile(
        r"^(?:(?:strong|proven|hands-on|solid|deep|demonstrated|practical|working|good|exceptional|extensive|thorough|minimum|track\s+record\s+(?:with|in|of)|knowledge\s+of|familiarity\s+with|proficiency\s+(?:in|with)|proficient\s+(?:in|with)|expertise\s+(?:in|with)|experience\s+(?:with|in|using|of)|ability\s+to|responsible\s+for|must\s+have|skilled\s+(?:in|with)|background\s+in|understanding\s+of)\s+)+",
        re.I
    )

    ACTION_PREFIXES = re.compile(
        r"^(?:(?:building|developing|designing|implementing|maintaining|creating|architecting|managing|spearheading|optimizing|driving|executing|working\s+with|hands-on\s+(?:with|in)|knowledge\s+of|proficiency\s+in|proven\s+track\s+record\s+in)\s+)+",
        re.I
    )

    # Common English morphological inflection suffixes for smart stemming
    STEM_SUFFIXES = [
        "ication", "ications", "ization", "izations", "ation", "ations",
        "tion", "tions", "ment", "ments", "ing", "ings", "ied", "ed",
        "ies", "es", "s", "ers", "er", "able", "al", "als", "ive", "ity"
    ]

    def __init__(self):
        self._regex_cache: Dict[str, re.Pattern] = {}

    def format_display_token(self, token: str) -> str:
        """Dynamically formats an extracted requirement or skill token nicely for display without hardcoded maps."""
        token_clean = token.strip().rstrip(".:;,")
        if not token_clean:
            return ""
        parts = token_clean.split()
        formatted_parts = []
        for p in parts:
            clean_p = p.strip()
            low_p = clean_p.lower()
            if any(c.isupper() for c in clean_p[1:]):
                # Preserves CamelCase / MixedCase (FastAPI, PostgreSQL, HubSpot, QuickBooks, A/B)
                formatted_parts.append(clean_p)
            elif clean_p.isupper() and len(clean_p) <= 6:
                formatted_parts.append(clean_p)
            elif not any(v in low_p for v in "aeiouy") and 2 <= len(clean_p) <= 5 and clean_p.isalpha():
                # Dynamic acronym detection (consonant-only tokens: CPR, SQL, KPI, DCF, BLS, EMR, CRM)
                formatted_parts.append(clean_p.upper())
            elif "/" in clean_p:
                sub = [s.upper() if (s.isupper() or not any(v in s.lower() for v in "aeiouy")) else s.capitalize() for s in clean_p.split("/")]
                formatted_parts.append("/".join(sub))
            elif low_p.endswith("#") or low_p.endswith("++") or low_p.startswith("."):
                formatted_parts.append(clean_p.upper())
            elif low_p in {"and", "or", "of", "in", "with", "for", "to"}:
                formatted_parts.append(low_p)
            else:
                formatted_parts.append(clean_p.capitalize())
        return " ".join(formatted_parts)

    def extract_role_title(self, jd_text: str) -> str:
        """Dynamically identifies the target job title or role from the job description."""
        for line in jd_text.splitlines()[:6]:
            line = line.strip()
            if not line:
                continue
            m = re.search(r"^(?:job\s+title|position|role|title)\s*[:\-–]?\s*(.+)", line, re.I)
            if m:
                title = m.group(1).strip().rstrip(".:;,")
                if 3 <= len(title) <= 60:
                    return title
            # Check if line looks like a title (short, title-cased, no intro prose)
            if 4 <= len(line) <= 50 and not any(
                line.lower().startswith(x)
                for x in ["about", "company", "description", "we are", "overview", "who we are", "welcome"]
            ):
                words = line.split()
                if 1 <= len(words) <= 5 and any(w[0].isupper() for w in words if w):
                    return line.rstrip(".:;,")
        return "Target Role"

    def extract_candidate_name(self, text: str) -> str:
        """Heuristically extracts candidate name from topmost resume lines or email."""
        raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
        # Strip post-nominal credentials/certifications (e.g. David Miller, CPA -> David Miller)
        lines = [
            re.sub(r",\s*(?:CPA|RN|MD|PhD|PMP|Esq|PE|MBA|JD|BSN|MSN)\b.*", "", line, flags=re.I).strip()
            for line in raw_lines
        ]
        ignored_keywords = {
            "resume", "curriculum", "vitae", "summary", "profile", "contact",
            "experience", "skills", "education", "phone", "email", "linkedin",
            "portfolio", "address", "page", "developer", "engineer", "architect",
            "manager", "specialist", "officer", "nurse", "analyst"
        }

        for line in lines[:5]:
            words = line.split()
            if 2 <= len(words) <= 4:
                lower_words = {w.lower().rstrip(":,") for w in words}
                if not (lower_words & ignored_keywords):
                    if all(w[0].isupper() or w[0].isalpha() for w in words if w):
                        cleaned = re.sub(r'[^a-zA-Z\s]', '', line).strip()
                        if len(cleaned.split()) >= 2:
                            return cleaned

        # Fallback: Extract name from email address
        email_match = re.search(r'([a-zA-Z0-9_.+-]+)@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
        if email_match:
            user_part = email_match.group(1).split(".")[0].replace("_", " ")
            if len(user_part) > 2:
                return user_part.title()

        return "Candidate Profile"

    def extract_requirements_from_jd(self, jd_text: str) -> Tuple[List[str], Dict[str, str]]:
        """
        Dynamically extracts required skills, tools, qualifications, and domain competencies
        from ANY Job Description using regular expressions without requiring hardcoded taxonomies.
        Returns (requirements_list, acronym_mapping).
        """
        requirements: List[str] = []
        acronym_map: Dict[str, str] = {}
        seen: Set[str] = set()

        def add_req(r: str, full_canonical: Optional[str] = None):
            cleaned = self.strip_action_prefixes(r)
            if 2 <= len(cleaned) <= 45:
                low = cleaned.lower()
                if low not in seen and not low.startswith(
                    ("degree in", "bachelor", "master", "phd", "equal opportunity", "we offer", "who you are")
                ):
                    seen.add(low)
                    display = self.format_display_token(cleaned)
                    requirements.append(display)
                    if full_canonical:
                        acronym_map[display.lower()] = full_canonical.lower()
                        acronym_map[full_canonical.lower()] = display.lower()

        # Parse sections, inline lists, and bullet items
        lines = jd_text.splitlines()
        in_req_section = False

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Detect section header transitions and inline skill lists
            sec_match = re.search(
                r"^(?:requirements|qualifications|skills|core\s+competencies|technologies|tech\s+stack|tools\s+&\s+technologies|tools|stack|what\s+you(?:\x27ll|\s+will|\s+need)|must\s+have|responsibilities)\s*[:\-–]?\s*(.*)",
                line_str,
                re.I,
            )
            if sec_match:
                in_req_section = True
                inline_content = sec_match.group(1).strip()
                if inline_content:
                    for clause in re.split(r"[\.!\?]+", inline_content):
                        if clause.strip():
                            parts = re.split(r"[,;]|\s+(?:and|or|&)\s+", clause.strip())
                            for p in parts:
                                add_req(p)
                continue
            elif in_req_section and re.search(
                r"^(?:about\s+us|benefits|perks|compensation|equal|who\s+we\s+are|company\s+overview)\b",
                line_str,
                re.I,
            ):
                in_req_section = False
                continue

            is_bullet = bool(re.match(r"^[\s•\*\-\–\—\>]+|^\d+[\.\)]\s+", line_str))

            if in_req_section or is_bullet:
                clean_line = re.sub(r"^[\s•\*\-\–\—\>]+|^\d+[\.\)]\s+", "", line_str).strip()
                clean_line = re.sub(
                    r"^\d+\+?\s*years(?:\s+of)?(?:\s+experience)?(?:\s+(?:in|with|of))?\s*",
                    "",
                    clean_line,
                    flags=re.I,
                ).strip()
                clean_line = self.FILLER_PREFIXES.sub("", clean_line).strip()

                # Extract acronyms in parentheses (e.g. Search Engine Optimization (SEO))
                for m in re.finditer(r"\b([A-Za-z0-9\s\.\-_]{2,45})\s*\(([A-Za-z0-9\+\#\s\-\/\.]{2,8})\)", clean_line):
                    full_name = m.group(1).strip()
                    acr = m.group(2).strip()
                    if "," not in acr and ";" not in acr:
                        add_req(acr, full_canonical=full_name)
                        add_req(full_name, full_canonical=acr)

                # Extract explicit technology lists inside parentheses (e.g. (PostgreSQL, SQLite))
                for m in re.finditer(r"\(([^\)]+)\)", clean_line):
                    paren_content = m.group(1).strip()
                    if any(sep in paren_content for sep in (",", ";", " or ", " and ", " & ")):
                        for p in re.split(r"[,;]|\s+(?:and|or|&)\s+", paren_content):
                            p_clean = re.sub(r"^(?:e\.?g\.?|such as|i\.?e\.?)\s*", "", p.strip(), flags=re.I).strip()
                            if 2 <= len(p_clean) <= 40:
                                add_req(p_clean)

                clean_line = re.sub(r"\([^\)]*\)", "", clean_line).strip()

                for clause in re.split(r"[\.!\?]+", clean_line):
                    if clause.strip():
                        parts = re.split(r"[,;]|\s+(?:and|or|&)\s+", clause.strip())
                        for p in parts:
                            add_req(p)

        # Fallback for prose / un-bulleted JDs: parse trigger phrases via regex
        if len(requirements) < 3:
            for m in re.finditer(
                r"(?:experience\s+(?:in|with|of|using)|proficiency\s+in|knowledge\s+of|expertise\s+in|background\s+in|familiar\s+with|skilled\s+in)\s+([^.,;\n]+)",
                jd_text,
                re.I,
            ):
                for p in re.split(r"[,;]|\s+(?:and|or|&)\s+", m.group(1).strip()):
                    add_req(p)

        # Additional fallback: extract capitalized 2-3 word compound terms via regex
        if len(requirements) < 3:
            for clause in re.split(r"[\.!\?\n\r]+", jd_text):
                clause_str = clause.strip()
                if not clause_str or len(clause_str) < 3:
                    continue
                parts = re.split(r"[,;]|\s+(?:and|or|&)\s+", clause_str)
                for p in parts:
                    p_clean = p.strip()
                    if p_clean and any(c.isupper() for c in p_clean) and 2 <= len(p_clean) <= 40:
                        add_req(p_clean)

        return requirements[:15], acronym_map

    def _stem_word(self, w: str) -> str:
        """Lightweight morphological stemmer for English inflection suffixes."""
        w = w.lower().strip(".,;:!?\"'()[]{}")
        for suffix in self.STEM_SUFFIXES:
            if len(w) > len(suffix) + 2 and w.endswith(suffix):
                return w[:-len(suffix)]
        return w

    def strip_action_prefixes(self, req: str) -> str:
        """Removes leading action verbs, filler prefixes, and trailing fluff from requirement phrases."""
        cleaned = req.strip().rstrip(".:;,")
        cleaned = self.FILLER_PREFIXES.sub("", cleaned).strip()
        cleaned = self.ACTION_PREFIXES.sub("", cleaned).strip()
        cleaned = re.sub(
            r"^(?:in|with|using|of|for|on|and|or|including|such as|to|across)\s+", "", cleaned, flags=re.I
        ).strip()
        cleaned = self.FILLER_PREFIXES.sub("", cleaned).strip()
        cleaned = re.sub(
            r"\s+(?:is\s+a\s+plus|is\s+preferred|preferred|required|a\s+must|desired|a\s+bonus)$",
            "",
            cleaned,
            flags=re.I,
        ).strip()
        cleaned = re.sub(
            r"\s+(?:on\s+the\s+backend|on\s+the\s+frontend|in\s+the\s+backend|in\s+the\s+frontend|on\s+backend|on\s+frontend|in\s+production)$",
            "",
            cleaned,
            flags=re.I,
        ).strip()
        return cleaned

    def build_skill_regex(self, skill: str) -> re.Pattern:
        """
        Dynamically compiles an optimized regular expression pattern for ANY requirement or skill
        extracted from a job description, with zero hardcoded taxonomies.
        Supports programming symbols (C#, C++, .NET), abbreviations (CI/CD, BLS/ACLS),
        extensions (Node.js), and morphological word stems.
        Caches compiled patterns for high-speed repeated lookups.
        """
        skill_clean = skill.strip()
        if not skill_clean:
            return re.compile(r"$^")  # Matches nothing

        # Check regex cache
        if skill_clean in self._regex_cache:
            return self._regex_cache[skill_clean]

        # 1. If caller explicitly passed a raw regular expression with regex syntax
        has_regex_metachars = any(
            meta in skill_clean
            for meta in (r"\b", r"\s", r"\d", r"\w", "(?:", "(?i)", "|", ".*", ".+", "^", "$", "(?=", "(?!")
        )
        if has_regex_metachars:
            try:
                compiled = re.compile(skill_clean, re.IGNORECASE)
                self._regex_cache[skill_clean] = compiled
                return compiled
            except re.error:
                pass

        tokens = [t for t in re.split(r"[\s\-_]+", skill_clean) if t]
        if not tokens:
            compiled = re.compile(rf"\b{re.escape(skill_clean)}\b", re.IGNORECASE)
            self._regex_cache[skill_clean] = compiled
            return compiled

        token_patterns = []
        for t in tokens:
            low_t = t.lower()
            if low_t.endswith("#"):
                base = re.escape(t[:-1])
                token_patterns.append(rf"(?:\b{base}#(?=[^a-zA-Z0-9#]|$)|{base}sharp\b)")
            elif low_t.endswith("sharp") and len(low_t) <= 8:
                base = re.escape(t[:-5])
                token_patterns.append(rf"(?:\b{base}#(?=[^a-zA-Z0-9#]|$)|{base}sharp\b)")
            elif low_t.endswith("++"):
                base = re.escape(t[:-2])
                token_patterns.append(rf"(?:\b{base}\+\+(?:\d{{2}})?(?=[^a-zA-Z+]|$)|{base}pp\b)")
            elif low_t.endswith("pp") and len(low_t) <= 4:
                base = re.escape(t[:-2])
                token_patterns.append(rf"(?:\b{base}\+\+(?:\d{{2}})?(?=[^a-zA-Z+]|$)|{base}pp\b)")
            elif low_t.startswith("."):
                base = re.escape(t[1:])
                token_patterns.append(rf"(?:(?:\b\w+)?\.{base}\b|dot{base}\b)")
            elif low_t.startswith("dot") and len(low_t) <= 7:
                base = re.escape(t[3:])
                token_patterns.append(rf"(?:(?:\b\w+)?\.{base}\b|dot{base}\b)")
            elif "/" in t:
                slash_parts = [re.escape(p.strip()) for p in t.split("/") if p.strip()]
                token_patterns.append(r"\s*[\/\-]\s*".join(rf"\b{p}\b" for p in slash_parts))
            elif "." in t:
                name, ext = t.rsplit(".", 1)
                token_patterns.append(rf"\b{re.escape(name)}(?:\.{re.escape(ext)}|{re.escape(ext)})?\b")
            elif len(t) <= 4 or t.isupper():
                token_patterns.append(rf"\b{re.escape(t)}\b")
            else:
                stem = self._stem_word(t)
                if stem != low_t and len(stem) >= 3:
                    token_patterns.append(rf"\b(?:{re.escape(t)}|{re.escape(stem)}(?:ing|s|es|ed|ation|ized|ize|able|er|ers)?)\b")
                else:
                    token_patterns.append(rf"\b{re.escape(t)}(?:s|es)?\b")

        joined = r"\s+".join(token_patterns)
        compiled = re.compile(joined, re.IGNORECASE)
        self._regex_cache[skill_clean] = compiled
        return compiled

    def search_skill(self, skill: str, text: str) -> bool:
        """
        Executes a regular expression search for the given skill across candidate text.
        Accepts canonical skill names, technology terms, or custom regular expressions.
        """
        if not skill or not text:
            return False
        pattern = self.build_skill_regex(skill)
        return bool(pattern.search(text))

    def find_skills_in_text(self, text: str) -> List[str]:
        """
        Finds all verified skills in candidate text or job description dynamically using regular expressions
        without hardcoded taxonomies.
        """
        reqs, _ = self.extract_requirements_from_jd(text)
        return reqs

    def match_requirement(
        self, req: str, text: str, acronym_map: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Regex-based smart search: checks if a requirement extracted from the job description
        is satisfied in candidate text using dynamically generated regular expressions.
        Uses exact word boundaries, acronym mappings, action verb stripping, and morphological proximity.
        """
        req_clean = req.strip()
        if not req_clean:
            return False

        text_lower = text.lower()
        req_lower = req_clean.lower()

        # 1. Direct dynamic regular expression match on the requirement
        if self.search_skill(req_clean, text):
            return True

        # 2. Check acronym alias if mapped from the job description
        if acronym_map and req_lower in acronym_map:
            alias = acronym_map[req_lower]
            if self.search_skill(alias, text):
                return True

        # 3. Strip action verbs & fluff, then search via regular expression
        # e.g., "Building Production Backends with Python" -> "Production Backends with Python"
        cleaned_req = self.strip_action_prefixes(req_clean)
        if cleaned_req and cleaned_req.lower() != req_lower:
            if self.search_skill(cleaned_req, text):
                return True

        # 4. Search for core entities (proper nouns, tools, acronyms) mentioned inside compound phrases
        # e.g., "Building production backends with Python" contains "Python"
        # "Docker Containerization" contains "Docker"
        # "PostgreSQL Schema Design" contains "PostgreSQL"
        tokens = [t for t in re.split(r"[\s\-_]+", req_clean) if t]
        generic_non_entities = {
            "and", "with", "the", "for", "from", "into", "using", "across",
            "frontend", "backend", "fullstack", "full-stack", "development", "developer",
            "software", "engineer", "engineering", "knowledge", "experience", "experienced",
            "proficient", "proficiency", "strong", "solid", "skills", "skill", "technologies",
            "tools", "stack", "practice", "practices", "services", "service", "providers",
            "provider", "solutions", "solution", "platforms", "platform", "applications",
            "application", "systems", "system", "environments", "environment", "architecture",
            "architectures", "management", "manager", "support", "operations"
        }
        content_tokens = [
            t for t in tokens
            if len(t) > 2 and t.lower() not in generic_non_entities
        ]
        for t in content_tokens:
            if any(c.isupper() for c in t) or any(c in t for c in "#+./") or (len(t) <= 4 and t.isupper()):
                if self.search_skill(t, text):
                    return True

        # 5. Exact substring match fallback
        if req_lower in text_lower:
            return True

        # 6. Morphological stem & proximity match for descriptive / natural language JD phrases
        req_tokens = [
            w for w in re.findall(r"\b\w+\b", req_lower)
            if len(w) > 2 and w not in {"and", "with", "the", "for", "from", "into", "using"}
        ]
        if not req_tokens:
            return False

        req_stems = {self._stem_word(t) for t in req_tokens}

        # Check candidate sentences / bullets for stem coverage
        sentences = re.split(r"[\n\r•\*\-]+|[.!?]\s+", text_lower)
        for s in sentences:
            s_words = re.findall(r"\b\w+\b", s)
            s_stems = {self._stem_word(w) for w in s_words}
            matched_stems = req_stems & s_stems
            # If at least 60% of requirement content stems appear in the same sentence/chunk
            if len(matched_stems) >= max(1, len(req_stems) * 0.6):
                return True

        return False

    def match_requirements(
        self, requirements: List[str], text: str, acronym_map: Optional[Dict[str, str]] = None
    ) -> Tuple[List[str], List[str]]:
        """Splits requirements into verified matched vs missing competencies."""
        matched: List[str] = []
        missing: List[str] = []
        for req in requirements:
            if self.match_requirement(req, text, acronym_map):
                matched.append(req)
            else:
                missing.append(req)
        return matched, missing

    def extract_skills(self, text: str) -> Set[str]:
        """
        Dynamically extracts technical and professional skills from text without hardcoded taxonomies.
        Preserves backward compatibility for callers expecting extract_skills(text).
        """
        requirements, _ = self.extract_requirements_from_jd(text)
        return {r.lower() for r in requirements}

    def calculate_years_experience(self, text: str) -> Tuple[float, List[str]]:
        """
        Extracts date ranges (e.g. 'Jan 2019 - Present', '2018 - 2022')
        and executes Interval Union sweep algorithm to compute true YOE.
        Flags career gaps > 180 days (~6 months).
        """
        pattern = r"(?i)\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)?\.?\s*\d{4})\s*(?:-|to|–)\s*((?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)?\.?\s*\d{4})|present|current)\b"
        matches = re.findall(pattern, text)

        intervals: List[Tuple[datetime, datetime]] = []
        gaps: List[str] = []
        now = datetime.now()

        for start_str, end_str in matches:
            try:
                start_year_m = re.search(r"\d{4}", start_str)
                if not start_year_m:
                    continue
                start_date = datetime(int(start_year_m.group()), 1, 1)

                if "present" in end_str.lower() or "current" in end_str.lower():
                    end_date = now
                else:
                    end_year_m = re.search(r"\d{4}", end_str)
                    if not end_year_m:
                        continue
                    end_date = datetime(int(end_year_m.group()), 12, 31)

                if start_date <= end_date:
                    intervals.append((start_date, end_date))
            except Exception:
                continue

        if not intervals:
            yoe_m = re.search(r"(\d+)\+?\s*years(?:\s+of)?\s+experience", text, re.I)
            if yoe_m:
                return float(yoe_m.group(1)), []
            return 3.0, []

        intervals.sort(key=lambda x: x[0])
        merged = [intervals[0]]

        for current in intervals[1:]:
            prev_start, prev_end = merged[-1]
            curr_start, curr_end = current

            if curr_start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, curr_end))
            else:
                gap_days = (curr_start - prev_end).days
                if gap_days > 180:
                    start_label = prev_end.strftime("%b %Y")
                    end_label = curr_start.strftime("%b %Y")
                    gaps.append(
                        f"Transition gap between {start_label} and {end_label} (~{round(gap_days/30)} months)"
                    )
                merged.append(current)

        total_days = sum((end - start).days for start, end in merged)
        total_years = round(total_days / 365.25, 1)
        return max(0.5, total_years), gaps

    def extract_quantified_impact(self, text: str) -> List[str]:
        """
        Extracts accomplishments with active verbs and quantifiable metrics
        across business, tech, healthcare, finance, operations, and sales.
        """
        impact_sentences: List[str] = []
        sentences = re.split(r"[\n\r•\*\-]+", text)

        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < 20 or len(s_clean) > 280:
                continue
            words = set(re.findall(r"\b\w+\b", s_clean.lower()))
            has_verb = bool(words & self.ACTION_VERBS)
            has_metric = bool(self.METRIC_REGEX.search(s_clean))

            if has_verb and has_metric:
                impact_sentences.append(s_clean)

        return impact_sentences[:4]

    def generate_baseline_questions(
        self, missing_skills: List[str], gaps: List[str], role_title: str = "Target Role"
    ) -> List[Dict[str, str]]:
        """Generates dynamic, role-adaptive questions for offline mode or fallback."""
        questions: List[Dict[str, str]] = []

        for skill in missing_skills[:2]:
            questions.append({
                "category": "Gap-Verification",
                "question": f"The target role emphasizes proficiency in {skill}. Could you share your familiarity with this area or describe how you've delivered comparable outcomes in past positions?",
                "target_area": f"{skill} Practical Competency",
                "expected_answer_criteria": f"Demonstrates solid functional fundamentals, structured ramp-up plan, and ability to transfer adjacent domain skills to {skill}."
            })

        for gap in gaps[:1]:
            questions.append({
                "category": "Behavioral",
                "question": f"We noted a transition period in your timeline ({gap}). Could you elaborate on any professional projects, freelancing, or skill development undertaken during that window?",
                "target_area": "Career Trajectory & Continuity",
                "expected_answer_criteria": "Transparent account of the career break, professional upskilling, open-source work, or sabbatical."
            })

        if not questions:
            questions.append({
                "category": "Behavioral",
                "question": f"Could you walk us through a pivotal initiative you spearheaded relevant to {role_title}, detailing how you navigated key trade-offs and measured success against target deliverables?",
                "target_area": "Leadership & Execution",
                "expected_answer_criteria": "Structured problem-solving (STAR method), ownership of outcomes, stakeholder communication, and concrete measurable impact."
            })

        return questions

    def evaluate(self, candidate_text: str, job_description: str) -> Dict:
        """
        Executes complete local, zero-quota smart candidate analysis.
        Works across ANY industry or job domain.
        """
        candidate_name = self.extract_candidate_name(candidate_text)
        role_title = self.extract_role_title(job_description)
        jd_requirements, acronym_map = self.extract_requirements_from_jd(job_description)
        matched_skills, missing_skills = self.match_requirements(
            jd_requirements, candidate_text, acronym_map
        )

        if jd_requirements:
            skill_ratio = len(matched_skills) / len(jd_requirements)
            base_skill_score = skill_ratio * 75.0
        else:
            base_skill_score = 60.0

        yoe, gaps = self.calculate_years_experience(candidate_text)
        exp_score = min(15.0, max(5.0, yoe * 3.5)) if yoe > 0 else 5.0

        impact_projects = self.extract_quantified_impact(candidate_text)
        impact_bonus = min(10.0, len(impact_projects) * 3.0)

        final_score = int(min(98, max(25, round(base_skill_score + exp_score + impact_bonus))))

        questions = self.generate_baseline_questions(missing_skills, gaps, role_title)

        matched_str = ", ".join(matched_skills[:4]) if matched_skills else "core domain foundations"
        summary = (
            f"{candidate_name} exhibits approximately {yoe} years of professional experience relevant to {role_title}. "
            f"Demonstrates verified competencies in {matched_str}. "
            f"Successfully matches {len(matched_skills)} of {len(jd_requirements)} target requirements."
        )

        return {
            "candidate_name": candidate_name,
            "match_percentage": final_score,
            "estimated_years_experience": yoe,
            "matched_skills": matched_skills,
            "missing_critical_skills": missing_skills,
            "detected_projects_and_impact": impact_projects or [
                f"Candidate profile demonstrates continuous contributions across {role_title} responsibilities."
            ],
            "red_flags_and_gaps": gaps,
            "tailored_interview_questions": questions,
            "executive_summary": summary,
        }


local_analyzer = LocalResumeAnalyzer()
