# Candidate Evaluation & Extraction

Kayatix automates the technical vetting and screening process for engineering and knowledge roles using Retrieval-Augmented Generation (RAG) and multi-provider Cloud LLMs.

---

## 📄 Resume PDF Screening (`/screener`)

* **Accepted Formats**: Standard resume PDFs, Curriculum Vitae (CV), or LinkedIn "Save to PDF" exports.
* **Extraction Pipeline**:
  1. The server reads the PDF bytes via `pypdf`.
  2. Strips noise, excessive whitespace, redundant carriage returns, and headers/footers to conserve tokens.
  3. Decomposes the resume into semantic chunks (`technical_skills`, `professional_experience`, `engineering_projects`, `education_certifications`, `candidate_summary`).
  4. Synthesizes an evidence matrix against the JD benchmark and dispatches to the AI Cascade.
* **Scanned PDFs**:
  If a PDF contains fewer than 40 characters of selectable text, it is flagged as a scanned image rather than a selectable text document.

---

## 🌐 Portfolio & Website Extraction (`/portfolio`)

Candidates frequently link personal blogs, tech portfolios, or GitHub profiles.

* **Single-Page Application (SPA) Support**:
  Many modern developer portfolios are built with React, Vue, Next.js, or Nuxt.js where raw HTML contains only an empty `<div id="root"></div>`.
  Kayatix implements advanced multi-stage extraction:
  1. **GitHub Profiles**: Specialized handler extracting bio, pinned repositories, stars, and primary languages.
  2. **Next.js & SSR Data**: Automatically parses embedded `<script id="__NEXT_DATA__">` JSON payloads.
  3. **OpenGraph & Meta Tags**: Extracts title, description, and author metadata.
  4. **SPA Bundle String Discovery**: Inspects client-side JavaScript bundle chunks to reconstruct portfolio projects.
* **Fallback Direct Text Input**:
  If a portfolio requires login, blocks scrapers with Cloudflare/HTTP 403, or is a pure canvas app, recruiters can paste the candidate's bio or project text directly into the fallback text area.

---

## 📊 Calibrated Evaluation Scorecards

Each evaluation produces a comprehensive assessment:
1. **Candidate Full Legal Name**: Extracted from header/contact details.
2. **Match Score (0–100%)**:
   - `85% - 100%`: Exceptional Fit (Green Badge)
   - `70% - 84%`: Strong Hireable Fit (Green Badge)
   - `50% - 69%`: Moderate Fit / Development Opportunity (Yellow Badge)
   - `< 50%`: Low Fit (Red Badge)
3. **Estimated Years of Experience (YOE)**: Calculated strictly from commercial software engineering roles (unrelated non-tech jobs excluded).
4. **Matched Skills**: Competencies verified with production experience.
5. **Missing Critical Skills**: Non-negotiable core requirements absent from the profile.
6. **Detected Projects & Quantifiable Impact**: Concrete architectures, deliverables, and performance metrics.
7. **Red Flags & Timeline Gaps**: Unexplained career gaps > 6 months, brief tenure, or unverified claims.
8. **5–7 Tailored Interview Questions**: Concrete technical and behavioral questions categorized by tested skill area, complete with expected candidate answers.

---

## ⚡ Active Provider Caching & History

* Every evaluation computes a deterministic SHA-256 hash of `(Candidate Text + JD Text)`.
* Repeating an identical evaluation returns immediately from cache (`< 15ms`), saving LLM tokens and API quotas.
* **Active Provider Cache Invalidation**: The engine verifies that the cached provider is currently configured and active. If a cache entry belongs to an unconfigured provider (e.g. an old Gemini record when only Groq is active), the cache is automatically invalidated and a live evaluation is triggered using the active LLM cascade.
* **Force Refresh**: Users can pass `force_refresh=true` to bypass cache and regenerate a fresh evaluation.


