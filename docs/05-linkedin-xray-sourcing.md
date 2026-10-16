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

### Step 3: Configure API Key Restrictions (Fixing `API_KEY_SERVICE_BLOCKED`)
If you see the error:
> `Requests to Custom Search are blocked (API_KEY_SERVICE_BLOCKED / PERMISSION_DENIED)`

Your Google Cloud API Key has restrictive security rules that block `customsearch.googleapis.com`. To fix this:

1. Open the [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
2. Click on the API Key you pasted into Kayatix Settings.
3. Scroll down to the **API restrictions** section:
   - **Option A (Secure / Recommended)**: Keep **"Restrict key"** selected. In the **Select APIs** dropdown, search for **Custom Search API** and check its box. Ensure both your Gemini API and Custom Search API are checked if sharing the key.
   - **Option B (Unrestricted)**: Change the selection to **"Don't restrict key"**.
4. Click **Save** at the bottom.
5. Wait **1 to 3 minutes** for Google's edge servers to propagate the change.

---

## 🚀 Zero-Setup Alternatives (No Google Cloud Key Needed!)

If you do not have a Google Cloud Console account or your API key is blocked:

1. **1-Click Direct Google Search**:
   - On the Sourcing page (`/sourcing`), fill in the role, location, and skills.
   - Click the blue **"Open Direct Search on Google"** button.
   - Google opens in a new tab with the exact pre-composed Boolean dork query with zero API keys required.
2. **Embedded CSE Search Widget**:
   - Click the **"CSE Widget (Zero Keys)"** tab.
   - Search LinkedIn profiles interactively using Google's hosted search widget.

