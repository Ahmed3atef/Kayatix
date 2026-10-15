# Kayatix | A.Y.A.T. Engine
### *(Project AYAT — Automated Yield for Applicant & Talent)*
> **Alternative Technical Subtitle**: *AI-driven Yield & Analytics for Talent*

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6%20[standard]-009688.svg)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-V2.10.4-e92063.svg)](https://docs.pydantic.dev/)
[![Package Manager](https://img.shields.io/badge/Package%20Manager-uv-blueviolet.svg)](https://github.com/astral-sh/uv)
[![UI](https://img.shields.io/badge/UI-Jinja2%20%2B%20Bootstrap%205.3-7952b3.svg)](https://getbootstrap.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Resilience](https://img.shields.io/badge/High%20Availability-Multi--Provider%20Failover-success.svg)]()

---

## 🌟 About the Project & The A.Y.A.T. Name

**Kayatix** is an enterprise-grade Human Resources Automation and Talent Intelligence platform powered by **FastAPI**, **Pydantic V2**, **SQLAlchemy Async**, and a **Multi-Provider AI Fallback Engine**.

### The Engineering Rationale Behind A.Y.A.T.:
- **Official Technical Meaning**: **A.Y.A.T.** = **Automated Yield for Applicant & Talent**
- **Secondary Technical Designation**: **AI-driven Yield & Analytics for Talent**
- **Design Philosophy**: Designed to appear in technical documentation, repository registries, and enterprise architectures as a scientific talent-scoring engine, providing objective, data-backed candidate matching and sourcing automation.

---

## 📑 Table of Contents
1. [Core Features & Architecture](#1-core-features--architecture)
2. [Multi-Provider AI Fallback Cascade](#2-multi-provider-ai-fallback-cascade)
3. [Developer API Setup Guide & Credentials](#3-developer-api-setup-guide--credentials)
4. [System Installation & Quickstart (with uv)](#4-system-installation--quickstart-with-uv)
5. [Complete User & Operator Manual](#5-complete-user--operator-manual)
   - [5.1 Dashboard & Navigation](#51-dashboard--navigation)
   - [5.2 A.Y.A.T. Resume & LinkedIn PDF Screener](#52-ayat-resume--linkedin-pdf-screener)
   - [5.3 Deep Portfolio & Personal Website Analyzer](#53-deep-portfolio--personal-website-analyzer)
   - [5.4 100% Legal LinkedIn X-Ray Sourcing Engine](#54-100-legal-linkedin-x-ray-sourcing-engine)
   - [5.5 Evaluation History & SHA-256 Deduplication Cache](#55-evaluation-history--sha-256-deduplication-cache)
   - [5.6 Settings & Live Provider Diagnostics](#56-settings--live-provider-diagnostics)
6. [REST API Reference & cURL Examples](#6-rest-api-reference--curl-examples)
7. [Automated Testing Suite](#7-automated-testing-suite)
8. [Production Best Practices & FAQ](#8-production-best-practices--faq)

---

## 1. Core Features & Architecture

- **Unbiased Resume Screening & Benchmarking**: Parses PDF resumes and LinkedIn "Save to PDF" exports using `pypdf`, sanitizes noise, and benchmarks candidates deterministically against target Job Descriptions.
- **100% Legal Candidate Sourcing (Zero Account Bans)**:
  - **Google X-Ray Search Engine**: Discovers public LinkedIn profiles via Google Custom Search JSON API dorking without sending authenticated requests to LinkedIn servers.
- **Deep Portfolio & Personal Website Analysis**: Asynchronously scrapes and strips boilerplate from candidate personal blogs, technical portfolios, and GitHub readmes using `httpx` and `trafilatura`.
- **Tailored Interview Generation**: Dynamically drafts behavioral, technical, and timeline gap-verification questions with concrete expected answer criteria.
- **High Availability Multi-Provider AI Failover**:
  - Aggregates developer quotas across **Google AI Studio (Gemini 2.5 Flash)**, **Groq Cloud (Llama 3.3 70B)**, and **OpenRouter (Fallback Pool)**.
  - Transparently handles HTTP 429 rate limits via circuit-breaker fallback logic.
  - **SHA-256 Deduplication Cache**: Caches `(candidate_text + job_description)` checksums in SQLite to accelerate repetitive evaluations and eliminate redundant model calls.
- **Zero-Disk Configuration Requirement**:
  - **No `.env` file required on disk**. Out-of-the-box defaults are stored directly inside the SQLite database (`user_settings` table) and managed live through the Web UI.

---

## 2. Multi-Provider AI Fallback Cascade

```mermaid
flowchart TD
    Client["Client / HR Dashboard"] -->|"REST API / Web UI"| Core["FastAPI Application Core"]

    subgraph Ingestion ["Ingestion & Sourcing Services"]
        PDF["PDF Ingestion (pypdf)"]
        Scraper["Portfolio Scraper (httpx + trafilatura)"]
        XRay["Legal X-Ray Search (Google CSE API)"]
    end

    Core --> PDF
    Core --> Scraper
    Core --> XRay

    PDF --> Clean["Clean Normalized Text"]
    Scraper --> Clean

    Clean --> Hash["SHA-256 Checksum Engine"]
    Hash --> CacheDB[("Evaluation Cache & Settings (SQLite)")]

    CacheDB -->|Cache Hit| ReturnCached["Return Cached Result (Accelerated)"]

    CacheDB -->|Cache Miss| Router["Multi-Provider AI Router"]

    subgraph Cascade ["Multi-Provider AI Fallback Chain"]
        P1["Priority 1: Google Gemini 2.5 Flash\n(Structured JSON Native)"]
        P2["Priority 2: Groq Cloud Llama 3.3 70B\n(Ultra-Fast LPU Engine)"]
        P3["Priority 3: OpenRouter Fallback\n(Model Pool)"]

        P1 -->|"HTTP 429 / Error"| P2
        P2 -->|"HTTP 429 / Error"| P3
    end

    Router --> P1

    P1 -->|"Success"| Validate["Pydantic V2 Strict Validator"]
    P2 -->|"Success"| Validate
    P3 -->|"Success"| Validate

    Validate --> Persist["Persist to Cache DB"]
    Persist --> Response["Web UI Report & API Response"]
```

---

## 3. Developer API Setup Guide & Credentials

To enable multi-provider AI resilience, obtain developer API keys from the following portals:

| Service | Model / Engine | Default Recommended Limits | Portal Link |
| :--- | :--- | :--- | :--- |
| **Google AI Studio** | `gemini-2.5-flash` | 15 RPM, 1,500 RPD | [Google AI Studio](https://aistudio.google.com/) |
| **Groq Cloud** | `llama-3.3-70b-versatile` | 30 RPM, 14,400 RPD | [Groq Console](https://console.groq.com/keys) |
| **OpenRouter** | `meta-llama/llama-3.1-8b-instruct:free` | Standard rotating pool | [OpenRouter Keys](https://openrouter.ai/settings/keys) |
| **Google Custom Search API** | `Google Programmable Search` | 100 queries / day | [Google Cloud](https://console.cloud.google.com/) & [Search Engine](https://programmablesearchengine.google.com/) |

### Setting Up Google Custom Search (X-Ray Sourcing):
1. Navigate to [Programmable Search Engine](https://programmablesearchengine.google.com/) and create a new search engine.
2. Under **Sites to search**, add `linkedin.com/in/*` or select **Search the entire web**.
3. Copy the **Search engine ID** (`cx`) and set it into the app settings as `GOOGLE_CSE_CX_ID`.
4. Go to [Google Cloud Console](https://console.cloud.google.com/), enable the **Custom Search API**, generate an API Key, and set it as `GOOGLE_CSE_API_KEY`.

---

## 4. System Installation & Quickstart (with uv)

### Step 1: Clone the repository
```bash
git clone https://github.com/your-username/Kayatix.git
cd Kayatix
```

### Step 2: Create a Virtual Environment using `uv`
```bash
# Create virtual environment
uv venv

# Activate on Linux/macOS:
source .venv/bin/activate

# Or on Windows:
# .venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
uv pip install -r requirements.txt
```
*(Or install via pyproject.toml: `uv pip install -e .`)*

### Step 4: Launch the Kayatix Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> [!NOTE]
> **No `.env` file setup is necessary!** The application boots with functional SQLite defaults immediately. You can enter or modify your API keys at any time via the web settings interface at `http://localhost:8000/settings`.

---

## 5. Complete User & Operator Manual

### 5.1 Dashboard & Navigation
- Access the dashboard at **`http://localhost:8000/`**.
- **Top HR Analytics Metric Cards**: Live tracking of **Total Screened Candidates**, **Average Match Fit (%)**, **Qualified Shortlist (≥75%)**, and **Average Seniority (YOE)**, paired with a visual **Talent Pipeline Fit Distribution Bar**.
- **Quick-Access Launchpad**: Instant one-click routing to Screener, Portfolio Analyzer, X-Ray Sourcing, and Settings.
- **Recent Activity Table**: View candidate name, matched skills, overall score, provider used, and link directly to full reports.

---

### 5.2 Resume & LinkedIn PDF Screener
- **URL**: **`http://localhost:8000/screener`**
- **How to Use**:
  1. **Upload Resume**: Drag and drop any candidate PDF resume or LinkedIn profile export ("More..." > "Save to PDF").
  2. **Provide Job Description**: Paste target role criteria, or click one of the quick template presets:
     - *Senior Python / FastAPI Engineer*
     - *Lead Frontend Engineer (React/TypeScript)*
     - *DevOps / SRE Engineer*
  3. **Click "Run AI Evaluation"**:
     - The system extracts and sanitizes text via `pypdf`.
     - Generates a SHA-256 fingerprint of `(resume + JD)` to check the cache.
     - Routes to Google Gemini 2.5 Flash (or Groq failover if throttled).
     - Renders an interactive report card:
       - **Match Percentage** with color-coded gauge (Green for $\ge 75\%$, Yellow for $50-74\%$, Red for $<50\%$).
       - **Executive Fit Summary** written by the AI engine.
       - **Estimated Years of Experience**.
       - **Skill Badges**: Matched Skills (Green) vs Missing Critical Skills (Red).
       - **Detected Projects & Quantified Impact**: Highlighted bullet points verifying delivery.
       - **Red Flags & Timeline Gaps**: Unexplained career breaks, overlapping roles, or suspicious claims.
       - **Tailored Interview Questions**: Specific questions grouped by category (Technical, Behavioral, Timeline Verification) with the *expected answer signals* the interviewer should look for.

---

### 5.3 Deep Portfolio & Personal Website Analyzer
- **URL**: **`http://localhost:8000/portfolio`**
- **How to Use**:
  1. Enter the candidate's personal portfolio URL, engineering blog, or GitHub profile (e.g., `https://antfu.me`, `https://github.com/tiangolo`).
  2. Paste the target Job Description.
  3. Click **"Analyze Portfolio"**.
  4. The engine uses `trafilatura` to strip boilerplate headers, navigations, cookies, and footers, extracting high-value technical articles and project descriptions.
  5. The multi-provider AI synthesizes the extracted evidence against your JD requirements, scoring architectural maturity and real-world implementation depth.

---

### 5.4 100% Legal LinkedIn X-Ray Sourcing Engine
- **URL**: **`http://localhost:8000/sourcing`**
- **Why This Is 100% Legal & Safe**:
  - Scraping LinkedIn directly with headless browsers (Selenium/Playwright) or simulated requests triggers bot detection, violates LinkedIn terms of service, and leads to IP/account bans.
  - Kayatix uses **Google Programmable Search (Dorking)** to discover publicly indexed LinkedIn profiles via Google's Custom Search JSON API. Zero traffic touches LinkedIn's private servers.
- **How to Use**:
  1. **Job Title**: Enter target title (e.g. `Senior FastAPI Backend Engineer`).
  2. **Required Skills**: Add comma-separated keywords (e.g. `Python, PostgreSQL, Docker, AsyncIO`).
  3. **Location**: Specify the desired talent hub (e.g. `Cairo, Egypt` or `Berlin, Germany`).
  4. **Max Candidates**: Choose between 3 and 10 results.
  5. **Live Dork Preview**: Observe the real-time Google search query generated:
     ```text
     site:linkedin.com/in/ "Senior FastAPI Backend Engineer" "Python" "PostgreSQL" "Cairo, Egypt"
     ```
  6. Click **"Execute Google X-Ray Search"**:
     - View discovered candidate cards with candidate name, headline, geographic summary snippet, and a one-click button to open their public LinkedIn profile.

---

### 5.5 Evaluation History & SHA-256 Deduplication Cache
- **URL**: **`http://localhost:8000/history`**
- **How to Use**:
  1. Filter past evaluations in real time using the search box (filters by candidate name, matched skills, or provider).
  2. Filter by source (`PDF Resume` or `Portfolio Website`).
  3. Inspect the **Cache Indicator Badge** to see whether a report was freshly generated or served instantaneously from cache.
  4. Click **"View Full Report"** on any row to open the dedicated report view (`/evaluations/{id}`), complete with **Print / Save as PDF** styling.

---

### 5.6 Settings & Live Provider Diagnostics
- **URL**: **`http://localhost:8000/settings`**
- **No Disk `.env` Required**:
  - Configuration is persisted directly in SQLite (`user_settings` table) and loaded into application memory at startup.
- **Guided Form**:
  - Enter API keys for **Google AI Studio**, **Groq Cloud**, **OpenRouter**, and **Google CSE**.
  - Choose your subscription tier (`standard`, `pro`, `enterprise`).
  - Configure rate limits (RPM) and timeout thresholds.
- **One-Click Live Connectivity Diagnostics**:
  - Click **"Validate Credentials"** to run live handshake checks against Gemini, Groq, OpenRouter, and Google CSE.
  - The results modal provides clear green/red connection status badges and helpful troubleshooting advice.
- **Raw Configuration Editor**:
  - Switch to the **Raw Config Editor** tab to inspect or edit the configuration in standard environment variable syntax. It syncs directly back to the database.

---

## 6. REST API Reference & cURL Examples

Interactive Swagger documentation is available at **`http://localhost:8000/docs`** and ReDoc at **`http://localhost:8000/redoc`**.

### 1. Resume PDF Evaluation Endpoint
```bash
curl -X POST "http://localhost:8000/api/v1/evaluation/resume-pdf" \
  -F "job_description=Senior Backend Engineer with 5+ years in FastAPI and PostgreSQL." \
  -F "resume_file=@/path/to/resume.pdf"
```

### 2. Portfolio Website Evaluation Endpoint
```bash
curl -X POST "http://localhost:8000/api/v1/evaluation/portfolio-website" \
  -d "job_description=Lead Engineer with deep knowledge of distributed systems." \
  -d "portfolio_url=https://candidate-portfolio.dev"
```

### 3. Legal LinkedIn X-Ray Sourcing Endpoint
```bash
curl -X POST "http://localhost:8000/api/v1/sourcing/linkedin-xray" \
  -H "Content-Type: application/json" \
  -d '{
    "job_title": "Senior FastAPI Backend Engineer",
    "required_skills": ["Python", "PostgreSQL", "Docker"],
    "location": "Remote",
    "max_results": 5
  }'
```

### 4. Settings Management & Diagnostics Endpoints
```bash
# Fetch current settings
curl "http://localhost:8000/api/v1/settings"

# Test provider connectivity
curl -X POST "http://localhost:8000/api/v1/settings/validate"
```

---

## 7. Automated Testing Suite

The application includes comprehensive unit, integration, and UI view tests:

```bash
# Run all tests with pytest
pytest -v
```

### Test Coverage Highlights:
- **`test_ai_engine.py`**: Verifies deterministic SHA-256 hashing, markdown code-block JSON cleaning, Gemini primary execution, and transparent fallback to Groq and OpenRouter upon HTTP 429 errors.
- **`test_caching.py`**: Confirms that identical `(resume + JD)` inputs hit the SQLite cache without issuing new API requests.
- **`test_endpoints.py`**: Validates file format boundaries (rejecting non-PDFs), successful multi-part form parsing, and sourcing endpoints.
- **`test_services.py`**: Validates PDF text noise removal, scanned image detection, Trafilatura HTML stripping, and Google CSE error handling.
- **`test_settings.py`**: Validates database storage of settings, raw configuration updates, and provider connectivity diagnostics.
- **`test_views.py`**: Confirms that all Jinja2 templates (`/`, `/screener`, `/portfolio`, `/sourcing`, `/history`, `/settings`, `/evaluations/{id}`) render cleanly without errors.

---

## 8. Production Best Practices & FAQ

### Q1: What happens if an AI provider experiences rate-limiting (HTTP 429)?
> The engine automatically executes circuit-breaker fallback down the cascade: **Gemini 2.5 Flash** $\to$ **Groq Llama 3.3 70B** $\to$ **OpenRouter Fallback Pool**. The switch happens with sub-second failover and zero disruption to the end user. If all configured providers are temporarily unavailable, a descriptive `HTTP 503` informs the user to check their rate limits.

### Q2: How does the platform avoid violating LinkedIn's Terms of Service?
> Kayatix never logs into LinkedIn, never executes automated browser interactions on LinkedIn, and never makes requests directly to `linkedin.com`. Instead, it uses Google's authorized Custom Search JSON API to index publicly accessible profiles that Google has already indexed.

### Q3: Why does Kayatix not require a `.env` file?
> Typical terminal-based `.env` files create friction for HR specialists and non-technical recruiters. Kayatix initializes default settings inside SQLite on startup. All keys, subscription tiers, and rate limits can be entered, edited, and tested directly inside the browser at `/settings`.

### Q4: How is token usage minimized?
> 1. Resumes are sanitized with `pypdf`, removing formatting bloat and truncating to 18,000 characters (comfortably within standard model context limits).
> 2. SHA-256 hashing prevents any duplicate resume/JD combination from consuming additional tokens.
> 3. Strict JSON schemas eliminate the need for verbose reasoning chain round-trips.

---

## 📄 License
This project is open-source under the **MIT License**.
Developed with pride as **Kayatix | A.Y.A.T. Engine (Project AYAT)** — *Automated Yield for Applicant & Talent*.
