# Troubleshooting & Common Issues

A guide to diagnosing and solving common issues when running Kayatix.

---

## 1. Google Custom Search: `API_KEY_SERVICE_BLOCKED`

### Symptoms:
```text
Requests to Custom Search are blocked (API_KEY_SERVICE_BLOCKED / PERMISSION_DENIED)
```

### Cause:
The Google Cloud API key has API restrictions enabled that do not include the Custom Search API, or the Custom Search API is not activated on the GCP project.

### Solution:
1. Open the [Google Cloud API Library](https://console.cloud.google.com/apis/library/customsearch.googleapis.com) and click **Enable**.
2. Open [Google Cloud Credentials](https://console.cloud.google.com/apis/credentials), edit your API Key, and either select **"Don't restrict key"** or add **Custom Search API** to the allowed list.
3. Save and wait 1–3 minutes for changes to propagate.
4. *Alternative*: Use the **1-Click Direct Google Search** button on `/sourcing` to search immediately without an API key.

---

## 2. Gemini: `503 UNAVAILABLE` / High Demand Spikes

### Symptoms:
```text
Gemini connection failed: 503 UNAVAILABLE. This model is currently experiencing high demand.
```

### Cause:
Google occasionally experiences regional spikes on default endpoints like `gemini-1.5-flash`.

### Solution:
Kayatix automatically detects 503 responses and tries the modern alternative models:
* `gemini-3.8-flash`
* `gemini-3.6-flash`
* `gemini-3.5-flash`
* `gemini-3.5-flash-lite`

If all Gemini endpoints are momentarily congested, the engine automatically fails over to **Groq Cloud LPUs** (`openai/gpt-oss-120b`). Ensure you have a Groq key configured in Settings for 99.99% uptime redundancy.

---

## 3. PostgreSQL: `can't subtract offset-naive and offset-aware datetimes`

### Symptoms:
```text
asyncpg.exceptions.DataError: invalid input for query argument: can't subtract offset-naive and offset-aware datetimes
```

### Cause:
PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` columns reject Python `datetime.now(timezone.utc)` objects that contain timezone metadata (`tzinfo`).

### Solution:
Kayatix uses `utc_now() = datetime.now(timezone.utc).replace(tzinfo=None)` for all timestamp columns, ensuring seamless compatibility across both SQLite and PostgreSQL.

---

## 4. PostgreSQL: `column user_settings.database_url does not exist`

### Symptoms:
Occurs when connecting to an existing database created with an older schema version.

### Solution:
Kayatix includes self-healing schema migrations in `app/core/database.py` that execute on startup:
```sql
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS database_url VARCHAR(1024);
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS evaluation_mode VARCHAR(50) DEFAULT 'llm_cascade';
```
No manual SQL execution is required.

---

## 5. Portfolio Scraper: `HTTP 403 (Access Denied)`

### Symptoms:
Target candidate portfolio blocks web scraping.

### Solution:
1. Paste the candidate's bio, skills, or portfolio summary directly into the **"Direct Portfolio Bio / Summary"** fallback text box on `/portfolio`.
2. For LinkedIn profiles, export the profile as a PDF ("Save to PDF" on LinkedIn) and upload it to `/screener`.

