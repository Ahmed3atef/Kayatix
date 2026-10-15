import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple


class LocalResumeAnalyzer:
    """
    High-speed, zero-quota local resume and candidate benchmarking engine.
    Extracts structured data, matches skills, merges career intervals for true YOE,
    and detects quantified impact metrics deterministically.
    """

    TECHNICAL_SKILLS_TAXONOMY: Dict[str, List[str]] = {
        # Programming Languages
        "python": ["python", "python3", "py"],
        "javascript": ["javascript", "js", "ecmascript"],
        "typescript": ["typescript", "ts"],
        "golang": ["golang", "go language"],
        "rust": ["rust", "rustlang"],
        "java": ["java", "jvm"],
        "c++": ["c++", "cpp"],
        "c#": ["c#", "csharp", ".net"],
        "php": ["php"],
        "ruby": ["ruby", "rails"],
        "sql": ["sql", "rdbms", "relational database"],
        "bash": ["bash", "shell", "powershell", "zsh"],

        # Frameworks & Libraries
        "fastapi": ["fastapi"],
        "django": ["django", "django rest framework", "drf"],
        "flask": ["flask"],
        "react": ["react", "react.js", "reactjs"],
        "vue": ["vue", "vue.js", "vuejs"],
        "angular": ["angular", "angularjs"],
        "nextjs": ["next.js", "nextjs"],
        "nodejs": ["node.js", "nodejs", "node"],
        "express": ["express", "express.js"],
        "spring": ["spring boot", "spring framework", "spring"],

        # Databases & Caching
        "postgresql": ["postgresql", "postgres", "psql"],
        "mysql": ["mysql", "mariadb"],
        "mongodb": ["mongodb", "mongo"],
        "redis": ["redis", "valkey"],
        "elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
        "sqlite": ["sqlite", "sqlite3"],
        "cassandra": ["cassandra"],
        "dynamodb": ["dynamodb"],

        # Cloud & Infrastructure
        "docker": ["docker", "containerization", "containers"],
        "kubernetes": ["kubernetes", "k8s"],
        "aws": ["aws", "amazon web services", "ec2", "s3", "lambda", "ecs"],
        "gcp": ["gcp", "google cloud platform", "google cloud"],
        "azure": ["azure", "microsoft azure"],
        "terraform": ["terraform", "iac", "infrastructure as code"],
        "ansible": ["ansible"],
        "ci/cd": ["ci/cd", "continuous integration", "github actions", "gitlab ci", "jenkins"],
        "linux": ["linux", "ubuntu", "debian", "redhat", "centos"],

        # Architecture & Methodologies
        "microservices": ["microservices", "microservice", "service-oriented"],
        "rest_api": ["rest api", "restful", "rest apis", "rest"],
        "graphql": ["graphql"],
        "grpc": ["grpc", "protobuf"],
        "kafka": ["kafka", "apache kafka"],
        "rabbitmq": ["rabbitmq", "amqp"],
        "distributed_systems": ["distributed systems", "event-driven", "message queue"],

        # Testing & Tooling
        "git": ["git", "github", "gitlab"],
        "pytest": ["pytest"],
        "tdd": ["tdd", "test driven development", "unit testing"],
        "machine_learning": ["machine learning", "ml", "deep learning", "ai", "llm", "nlp"],
        "pytorch": ["pytorch", "torch"],
        "tensorflow": ["tensorflow", "keras"],
    }

    ACTION_VERBS: Set[str] = {
        "architected", "designed", "scaled", "optimized", "spearheaded",
        "implemented", "reduced", "increased", "migrated", "automated",
        "engineered", "streamlined", "developed", "led", "boosted",
        "maintained", "deployed", "refactored", "secured", "resolved"
    }

    def __init__(self):
        # Build inverted lookup for O(N) skill matching
        self.skill_lookup: Dict[str, str] = {}
        for canonical, aliases in self.TECHNICAL_SKILLS_TAXONOMY.items():
            for alias in aliases:
                self.skill_lookup[alias.lower()] = canonical

    def extract_candidate_name(self, text: str) -> str:
        """Heuristically extracts candidate name from topmost resume lines or email."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # Check first 5 non-empty lines for 2-3 capitalized words (standard resume header)
        ignored_keywords = {
            "resume", "curriculum", "vitae", "summary", "profile", "contact",
            "experience", "skills", "education", "phone", "email", "linkedin",
            "portfolio", "address", "page", "developer", "engineer", "architect"
        }
        
        for line in lines[:5]:
            words = line.split()
            if 2 <= len(words) <= 4:
                lower_words = {w.lower().rstrip(":,") for w in words}
                if not (lower_words & ignored_keywords):
                    # Check if words are capitalized / title case
                    if all(w[0].isupper() or w[0].isalpha() for w in words if w):
                        cleaned = re.sub(r'[^a-zA-Z\s]', '', line).strip()
                        if len(cleaned.split()) >= 2:
                            return cleaned

        # Fallback: Extract name from email address (e.g. john.doe@email.com -> John Doe)
        email_match = re.search(r'([a-zA-Z0-9_.+-]+)@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
        if email_match:
            user_part = email_match.group(1).split(".")[0].replace("_", " ")
            if len(user_part) > 2:
                return user_part.title()

        return "Candidate Profile"

    def extract_skills(self, text: str) -> Set[str]:
        """Extracts normalized technical skills using word boundaries."""
        text_lower = text.lower()
        found_skills = set()
        
        for alias, canonical in self.skill_lookup.items():
            # Use word boundaries for clean matching
            pattern = r'\b' + re.escape(alias) + r'\b'
            if re.search(pattern, text_lower):
                found_skills.add(canonical)
                
        return found_skills

    def calculate_years_experience(self, text: str) -> Tuple[float, List[str]]:
        """
        Extracts date ranges (e.g., '2019 - 2023', 'Jan 2021 - Present')
        and merges overlapping intervals to compute true years of experience.
        Also identifies timeline gaps (> 6 months) between consecutive roles.
        """
        pattern = r'(?i)\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)?\.?\s*\d{4})\s*(?:-|to|–)\s*(\d{4}|present|current)\b'
        matches = re.findall(pattern, text)

        intervals: List[Tuple[datetime, datetime]] = []
        gaps: List[str] = []
        now = datetime.now()

        for start_str, end_str in matches:
            try:
                start_year_match = re.search(r'\d{4}', start_str)
                if not start_year_match:
                    continue
                start_year = int(start_year_match.group())
                start_date = datetime(start_year, 1, 1)

                if "present" in end_str.lower() or "current" in end_str.lower():
                    end_date = now
                else:
                    end_year_match = re.search(r'\d{4}', end_str)
                    if not end_year_match:
                        continue
                    end_year = int(end_year_match.group())
                    end_date = datetime(end_year, 12, 31)

                if start_date <= end_date:
                    intervals.append((start_date, end_date))
            except Exception:
                continue

        if not intervals:
            # Fallback heuristic: search for single mentions like '5+ years of experience'
            yoe_mention = re.search(r'(\d+)\+?\s*years(?:\s+of)?\s+experience', text, re.I)
            if yoe_mention:
                return float(yoe_mention.group(1)), []
            return 3.0, []

        # Interval Union Algorithm: merge overlapping employment periods
        intervals.sort(key=lambda x: x[0])
        merged = [intervals[0]]

        for current in intervals[1:]:
            prev_start, prev_end = merged[-1]
            curr_start, curr_end = current

            if curr_start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, curr_end))
            else:
                # Detect gaps greater than 180 days (6 months)
                gap_days = (curr_start - prev_end).days
                if gap_days > 180:
                    gaps.append(
                        f"Unexplained gap between {prev_end.strftime('%b %Y')} and {curr_start.strftime('%b %Y')} (~{round(gap_days/30)} months)"
                    )
                merged.append(current)

        total_days = sum((end - start).days for start, end in merged)
        total_years = round(total_days / 365.25, 1)
        return max(0.5, total_years), gaps

    def extract_quantified_impact(self, text: str) -> List[str]:
        """Extracts sentences/bullets containing action verbs AND concrete quantified performance metrics."""
        impact_sentences: List[str] = []
        sentences = re.split(r'[\n\r•\*\-]+', text)
        metric_regex = re.compile(
            r'(\d+[\d,.]*\s*(?:%|x|k|m|million|billion|users|req/s|rps|ms|latency|reduction|increase|cost|uptime|throughput))',
            re.I,
        )

        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < 25 or len(s_clean) > 280:
                continue
            words = set(re.findall(r'\b\w+\b', s_clean.lower()))
            has_action_verb = bool(words & self.ACTION_VERBS)
            has_metric = bool(metric_regex.search(s_clean))

            if has_action_verb and has_metric:
                impact_sentences.append(s_clean)

        return impact_sentences[:4]

    def generate_baseline_questions(
        self, missing_skills: List[str], gaps: List[str]
    ) -> List[Dict[str, str]]:
        """Generates deterministic, template-based questions for offline mode or fallback."""
        questions: List[Dict[str, str]] = []

        for skill in missing_skills[:2]:
            display_skill = skill.replace("_", " ").title()
            questions.append({
                "category": "Technical Bridge",
                "question": f"The target job requirements specify {display_skill}. What comparable technologies have you worked with, and how would you approach adopting {display_skill} in our production environment?",
                "target_area": f"{display_skill} Practical Competency",
                "expected_answer_criteria": f"Demonstrates strong architectural fundamentals, ability to compare trade-offs, and a structured ramp-up plan for {display_skill}."
            })

        for gap in gaps[:1]:
            questions.append({
                "category": "Timeline Verification",
                "question": f"We noted a transition period in your timeline ({gap}). Could you elaborate on any professional projects, freelancing, or skill development undertaken during that window?",
                "target_area": "Career Trajectory & Continuity",
                "expected_answer_criteria": "Transparent account of the career break, professional upskilling, open-source work, or sabbatical."
            })

        if not questions:
            questions.append({
                "category": "System Architecture",
                "question": "Could you walk us through the most technically challenging project in your recent experience, explaining how you handled trade-offs and scaling?",
                "target_area": "Engineering Leadership & Problem Solving",
                "expected_answer_criteria": "Clear articulation of trade-offs, metrics, failure modes, and end-to-end design ownership."
            })

        return questions

    def evaluate(self, candidate_text: str, job_description: str) -> Dict:
        """
        Executes complete local, zero-quota deterministic candidate analysis.
        """
        candidate_name = self.extract_candidate_name(candidate_text)
        resume_skills = self.extract_skills(candidate_text)
        jd_skills = self.extract_skills(job_description)

        matched_skills = sorted(list(resume_skills & jd_skills))
        missing_skills = sorted(list(jd_skills - resume_skills))

        # Skill match percentage
        if jd_skills:
            skill_score = (len(matched_skills) / len(jd_skills)) * 100.0
        else:
            skill_score = 75.0

        yoe, gaps = self.calculate_years_experience(candidate_text)
        impact_projects = self.extract_quantified_impact(candidate_text)

        # Composite score: 60% skills, 25% experience weight, 15% quantified impact
        impact_bonus = min(15, len(impact_projects) * 4)
        experience_bonus = min(25, yoe * 3)
        final_score = int(min(98, max(25, (skill_score * 0.6) + experience_bonus + impact_bonus)))

        questions = self.generate_baseline_questions(missing_skills, gaps)

        matched_display = [s.replace("_", " ").title() for s in matched_skills]
        missing_display = [s.replace("_", " ").title() for s in missing_skills]

        summary = (
            f"{candidate_name} exhibits approximately {yoe} years of industry experience. "
            f"Demonstrates verified competencies in {', '.join(matched_display[:4]) if matched_display else 'core engineering fundamentals'}. "
            f"Successfully matches {len(matched_skills)} of {len(jd_skills)} target job requirements."
        )

        return {
            "candidate_name": candidate_name,
            "match_percentage": final_score,
            "estimated_years_experience": yoe,
            "matched_skills": matched_display,
            "missing_critical_skills": missing_display,
            "detected_projects_and_impact": impact_projects or [
                "Profile reflects sustained professional contributions across technical roles."
            ],
            "red_flags_and_gaps": gaps,
            "tailored_interview_questions": questions,
            "executive_summary": summary,
        }


local_analyzer = LocalResumeAnalyzer()
