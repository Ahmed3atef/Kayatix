# Job Description Templates

Job Description (JD) templates define the standard technical requirements, tenure benchmarks, and competency scorecards used to evaluate candidates across the platform.

---

## 📋 Out-of-the-Box Standard Templates

Kayatix ships with 6 production-grade role templates:

1. **Senior Backend Engineer (Python / FastAPI)**
   - Category: Engineering
   - Tests: FastAPI, PostgreSQL, Docker, AsyncIO, Pytest, RESTful API design.

2. **Frontend Engineer (React / TypeScript)**
   - Category: Engineering
   - Tests: React 18, TypeScript, TailwindCSS, State management (Redux/Zustand), Web Vitals.

3. **DevOps & Cloud Infrastructure Engineer**
   - Category: DevOps / Infrastructure
   - Tests: AWS, Kubernetes, Terraform, CI/CD pipelines, Prometheus & Grafana.

4. **Senior Product Manager (SaaS)**
   - Category: Product
   - Tests: Roadmapping, OKR delivery, user interviews, SQL analytics, A/B testing.

5. **AI / Machine Learning Engineer (LLMs & Generative AI)**
   - Category: AI / Data
   - Tests: Python, PyTorch, LangChain, fine-tuning, vector search.

6. **Senior Financial Analyst (FP&A)**
   - Category: Finance
   - Tests: DCF modeling, budgeting, Power BI, US GAAP / IFRS standards.

---

## 🛠️ Managing Templates

* **Adding New Templates**:
  - In Settings (`/settings`), switch to the **Job Description Templates** tab.
  - Click **Add New Template**, enter a title, category, and JD text, then save.
* **Auto-Populating in Screener**:
  - In the Resume Screener or Portfolio Analyzer, click the **"Load Template"** dropdown.
  - Selecting any template instantly populates the target Job Description field.
* **Resetting Defaults**:
  - Click **Reset Defaults** in Settings to restore standard out-of-the-box benchmarks.

---

## ⚙️ Frappe DocType Schemas & Database Synchronization

Kayatix manages default job templates and system presets via dedicated, Frappe-compliant DocType JSON schemas and default configuration files:

* **Frappe DocType Schema Architecture**:
  - **DocType Schemas & ORM Models**: Organized in the dedicated `models/` folder (e.g., `models/job_template.json`, `models/user_settings.json`, `models/user.json`).
  - Follows standard Frappe Framework DocType structure (`doctype`, `field_order`, `fields`) paired with generic dynamic SQLAlchemy model generation and database synchronization logic in `models/model.py`.
  - **Job Templates & System Defaults Fixtures**: Strictly split into dedicated fixtures in `fixtures/` (`fixtures/job_template.json` and `fixtures/user_settings.json`).
  - Validated by standard Pydantic models (`AppDefaultsSchema`, `JobTemplateSchema`, `SystemSettingsDefaultsSchema`).

* **`modified_timestamp` Change Detection & Synchronization**:
  - `fixtures/job_template.json` carries a `modified_timestamp` key (e.g. `"2026-10-16T19:00:00Z"`).
  - The database tracks the synced timestamp in `user_settings.job_templates_schema_timestamp`.
  - When the server boots (in `lifespan`) or when a sync is triggered, the system compares the JSON fixture's `modified_timestamp` against the database.
  - If the timestamp or content differs, it automatically synchronizes the modified schema into the database.
  - Reverse sync endpoint (`/export`) allows exporting database updates back into `fixtures/job_template.json` and `fixtures/user_settings.json` with a fresh timestamp.

* **API Endpoints**:
  - `GET /api/v1/settings/schema/defaults`: Returns active templates and system defaults schema.
  - `POST /api/v1/settings/schema/defaults/sync`: Synchronizes `fixtures/` templates into the database.
  - `POST /api/v1/settings/schema/templates/export`: Exports database templates to `fixtures/job_template.json` and `fixtures/user_settings.json`.
  - `GET /api/v1/settings/schema/doctype/{doctype_name}`: Returns the Frappe DocType JSON Schema for any specified DocType.




