# Kayatix Overview & Architecture

Welcome to **Kayatix**, the **A.Y.A.T. Engine** (*Automated Yield for Applicant & Talent*). Kayatix is an AI-powered HR copilot designed for elite technical recruiters, hiring managers, and talent acquisition teams.

![Kayatix Platform Banner](/static/img/kayatix-banner.png)

---

## 🎯 Core Capabilities

1. **Resume Screener (`/screener`)**:
   - Accepts candidate PDF resumes, scanned documents, and LinkedIn exports.
   - Evaluates profiles using a **calibrated 100-point Senior HR Bar Raiser rubric** (Core Competency, Seniority, STAR Impact, System Design, and Stability).
   - Generates an executive hiring verdict (`[STRONG HIRE]`, `[PROCEED]`, `[BORDERLINE]`, `[REJECT]`).
   - Produces 5–7 tailored technical and behavioral interview questions with expected candidate answers.

2. **Portfolio Analyzer (`/portfolio`)**:
   - Evaluates candidate personal websites, portfolios, blogs, and GitHub profiles.
   - Extracts production project evidence from modern Single-Page Applications (Next.js, React, Vue, OpenGraph metadata).
   - Includes a direct text fallback for login-protected or pure canvas portfolios.

3. **Legal LinkedIn X-Ray Sourcing (`/sourcing`)**:
   - Leverages Google Custom Search JSON API to locate publicly indexed candidate profiles on LinkedIn.
   - Zero direct scraping of LinkedIn servers — 100% compliant with LinkedIn terms and anti-bot regulations.
   - Includes 1-Click zero-setup Google search and embedded CSE search widgets.

4. **Multi-Provider AI Cascade**:
   - Primary: **Google Gemini** (`gemini-2.5-flash`, `gemini-2.5-flash-lite`).
   - Secondary: **Groq Cloud LPUs** (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`).
   - Tertiary: **Ollama Cloud** fallback (`beam`, `gemma4:31b`, `gpt-oss:120b`, `gpt-oss:20b`, `nemotron-3-nano:30b`, `nemotron-3-super`, `nemotron-3-ultra`).
   - Automatic model failover on rate limits (429) or high-demand spikes (503).

5. **Universal Database Backend**:
   - Seamless, zero-copy live switching between local embedded **SQLite** and cloud **PostgreSQL** (Neon, Supabase, AWS RDS, Docker).
   - Self-healing schema migrations.

---

## 🧭 Navigation & Editing

You can edit any section of this documentation directly on your machine:
* Files are stored in the `docs/` folder in your project workspace.
* Changes made to any `.md` file in `docs/` are **immediately reflected live** on this page without restarting the application!

