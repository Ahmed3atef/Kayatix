# Legal LinkedIn X-Ray Sourcing & Google Cloud Setup

Kayatix allows recruiters to source passive technical candidates using **Google X-Ray Dorking** over publicly indexed LinkedIn profiles without scraping LinkedIn directly or risking account bans.

---

## 🔍 How LinkedIn X-Ray Works

Instead of logging into LinkedIn or scraping profile pages with automated bots (which triggers HTTP 403 or LinkedIn account restrictions), Kayatix queries Google's public web index using legal search operators:

```text
site:linkedin.com/in/ "Job Title" AND "Location" AND "Skill 1" AND "Skill 2"
```

Google returns public search snippets containing the candidate's name, current headline, company, and location.

---

## 🛠️ Google Custom Search JSON API Setup

To enable automated in-app JSON parsing of candidate search results:

### Step 1: Obtain a Search Engine ID (`cx`)
1. Visit the [Google Programmable Search Engine Control Panel](https://programmablesearchengine.google.com/controlpanel/all).
2. Click **Add** to create a new search engine.
3. In **What to search?**, enter `linkedin.com/in/*`.
4. Name your search engine (e.g. `LinkedIn Recruiter Search`) and click **Create**.
5. In the Overview panel, copy the **Search engine ID** (`cx`, e.g. `c5c6e8ce160ff411e`).

### Step 2: Enable the Custom Search API in Google Cloud
1. Open the [Google Cloud API Library for Custom Search](https://console.cloud.google.com/apis/library/customsearch.googleapis.com).
2. Select your Google Cloud Project in the top project selector.
3. Click the blue **Enable** button.

### Step 3: Google's New Project Restrictions (`PERMISSION_DENIED`)

> [!WARNING]
> **Google Cloud Custom Search JSON API Deprecation Notice**
> Google has permanently **closed the legacy Custom Search JSON API (`customsearch.googleapis.com`) to newly created Google Cloud projects**.
> 
> If you see the following response in your server logs or UI:
> ```json
> {
>   "error": {
>     "code": 403,
>     "message": "This project does not have the access to Custom Search JSON API.",
>     "status": "PERMISSION_DENIED"
>   }
> }
> ```
> This indicates Google's backend has restricted the JSON API to grandfathered legacy projects only. Even with the API enabled in Google Cloud Console and an unrestricted API key, Google rejects calls from new projects.

---

## 🚀 Recommended Sourcing Methods (100% Free & Zero Key Required!)

Kayatix was specifically built with two built-in alternatives that bypass Google Cloud API keys and restrictions completely:

### 1. 1-Click Search on Google (0 Setup)
- On the **Sourcing** page (`/sourcing`), enter your job title, location, and key skills.
- Click the blue **"Open 1-Click Search on Google"** button.
- Google immediately opens in a new tab with your exact Boolean dork query (e.g. `site:linkedin.com/in/ "Job Title" AND "Location" AND "Skill 1"`).
- **Benefits**: Zero Google Cloud setup, zero quotas, zero billing, zero 403 errors, and 100% access to live LinkedIn candidates.

### 2. Free Google CSE Browser Widget
- On the **Sourcing** page, click the **"CSE Widget (Zero Key)"** tab.
- This tab loads Google's interactive search widget directly inside your browser using your Search Engine ID (`cx`).
- **Benefits**: 100% free, unlimited, and runs directly in the client without needing Google Cloud API keys or backend permissions.

### 3. Fixing `API_KEY_SERVICE_BLOCKED` (For Existing / Legacy Projects)
If you are using an existing GCP project that has access to Custom Search API, but your key has API restrictions:
1. Open [Google Cloud Credentials](https://console.cloud.google.com/apis/credentials).
2. Select your API Key.
3. Under **API restrictions**, choose **"Don't restrict key"** or ensure **"Custom Search API"** is checked.
4. Click **Save** and allow 2-3 minutes for propagation.

