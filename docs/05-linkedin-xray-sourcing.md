# Legal LinkedIn X-Ray Sourcing (Zero API Keys Architecture)

Kayatix allows recruiters to source passive technical candidates using **Google X-Ray Dorking** over publicly indexed LinkedIn profiles without scraping LinkedIn directly, without risking account bans, and **without requiring any Google Cloud API keys or billing**.

---

## 🔍 How LinkedIn X-Ray Works

Instead of logging into LinkedIn or scraping profile pages with automated bots (which triggers HTTP 403 or LinkedIn account restrictions), Kayatix queries Google's public web index using legal search operators:

```text
site:linkedin.com/in/ "Job Title" AND "Location" AND "Skill 1" AND "Skill 2"
```

Google returns public search snippets containing the candidate's name, current headline, company, and location.

---

## 🚀 Two Zero-Setup Sourcing Modes

### 1. Embedded Google CSE Search Widget (Inside Kayatix)
- Enter your role, location, and skills.
- Click **"Search in Google CSE Widget"**.
- Google's official Programmable Search Engine widget executes the search directly inside the browser pane using your Search Engine ID (`cx`).
- **100% Free &bull; Unlimited Queries &bull; Zero Google Cloud API Keys Required.**

### 2. 1-Click Direct Google Search (New Tab)
- Click **"Open 1-Click Search on Google (0 Setup)"**.
- Google opens in a new tab with the exact pre-composed Boolean dork query with zero configuration required.

---

## 🛠️ Obtaining Your Free Search Engine ID (`cx`)

You do **not** need a Google Cloud Console account or an API key. You only need a free Search Engine ID:

1. Visit the [Google Programmable Search Engine Control Panel](https://programmablesearchengine.google.com/controlpanel/all).
2. Click **Add** to create a new search engine.
3. In **What to search?**, enter `linkedin.com/in/*`.
4. Name your search engine (e.g. `LinkedIn Recruiter Search`) and click **Create**.
5. In the Overview panel, copy your **Search engine ID** (`cx`, e.g. `f3b25cba6a1c14966`).
6. Paste it into Kayatix at **Settings &rarr; Section 2 (Search Engine ID)** and click **Save**.

That's it! Your interactive search engine is now embedded and ready to source candidates forever with zero costs or restrictions.

