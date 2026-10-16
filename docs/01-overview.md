# Kayatix Overview & Architecture

Welcome to **Kayatix**, the **A.Y.A.T. Engine** (*Automated Yield for Applicant & Talent*). Kayatix is an AI-powered HR copilot designed for elite technical recruiters, hiring managers, and talent acquisition teams.

![Kayatix Platform Banner](/static/img/kayatix-banner.png)

---

## 🎯 Core Capabilities

1. **Resume Screener (`/screener`)**:
   - Accepts candidate PDF resumes and LinkedIn "Save to PDF" exports.
   - Cleans and normalizes text, stripping token waste.
   - Directly feeds content into real Cloud LLMs (Gemini / Groq / OpenRouter) for merit-based scoring (0-100%).
   - Generates 5–7 tailored technical and behavioral interview questions targeting verified gaps.

2. **Portfolio Analyzer (`/portfolio`)**:
   - Supports candidate personal websites, portfolios, blogs, and GitHub profiles.
   - Fully supports modern Single-Page Applications (Next.js `__NEXT_DATA__`, React, Vue, client-side JS bundles).
   - Provides a fallback text box for private or protected portfolios.

3. **Legal LinkedIn X-Ray Sourcing (`/sourcing`)**:
   - Leverages Google Custom Search JSON API to locate publicly indexed candidate profiles on LinkedIn.
   - Zero direct scraping of LinkedIn servers — 100% compliant with LinkedIn terms and anti-bot regulations.
   - Includes 1-Click zero-setup Google search and embedded CSE search widgets.

4. **Multi-Provider AI Cascade**:
   - Primary: **Google Gemini** (`gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`).
   - Secondary: **Groq Cloud LPUs** (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `llama-3.3-70b-versatile`).
   - Tertiary: **OpenRouter** fallback.
   - Automatic model failover on rate limits (429) or high-demand spikes (503).

5. **Universal Database Backend**:
   - Seamless, zero-copy live switching between local embedded **SQLite** and cloud **PostgreSQL** (Neon, Supabase, AWS RDS, Docker).
   - Self-healing schema migrations.

---

## 🧭 Navigation & Editing

You can edit any section of this documentation directly on your machine:
* Files are stored in the `docs/` folder in your project workspace.
* Changes made to any `.md` file in `docs/` are **immediately reflected live** on this page without restarting the application!

