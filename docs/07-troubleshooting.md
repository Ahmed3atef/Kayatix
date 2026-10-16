# Troubleshooting & Common Issues

A guide to diagnosing and solving common issues when running Kayatix.

---

## 1. Google Custom Search: `403 Forbidden / Project Does Not Have Access`

### Symptoms:
```text
Google Search API error (HTTP 403): This project does not have the access to Custom Search JSON API.
```

### Cause:
Google Cloud restricted programmatic access to the legacy Custom Search JSON API for all new Google Cloud projects. Automated in-app raw JSON calls are blocked even if enabled in the Google Cloud Console.

### Solution:
Kayatix provides two official, 100% free, unlimited zero-key alternatives:
1. **Embedded Google Programmable Search Widget**: Uses only your free Search Engine ID (`cx`). Renders directly inside Kayatix with zero Google Cloud API keys or billing required.
2. **1-Click Direct Google Sourcing**: Click **"Open 1-Click Search on Google (0 Setup)"** on `/sourcing` to search directly on Google with the pre-compiled Boolean dork string. Zero configuration required.

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

