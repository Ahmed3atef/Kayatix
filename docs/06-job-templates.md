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

5. **AI / Machine Learning Engineer (LLMs & RAG)**
   - Category: AI / Data
   - Tests: Python, PyTorch, LangChain/LlamaIndex, Vector Databases, fine-tuning.

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

## ⚙️ JSON Settings Schema & Database Synchronization

Kayatix manages default job templates, system presets, and RAG evaluation instructions via dedicated, descriptive JSON schema configurations:

* **Descriptive JSON Configuration Files**:
  - **Job Templates & System Defaults**: Located at `app/core/default_job_templates.json` (schema: `app/core/default_job_templates.schema.json`).
  - **RAG & AI Instructions**: Located at `app/core/rag_ai_instructions.json` (schema: `app/core/rag_ai_instructions.schema.json`).
  - Validated by standard Pydantic models (`AppDefaultsSchema`, `JobTemplateSchema`, `SystemSettingsDefaultsSchema`, `RAGAIInstructionSchema`).

* **`modified_timestamp` Change Detection & Synchronization**:
  - Each JSON file carries a `modified_timestamp` key (e.g. `"2026-10-16T19:00:00Z"`).
  - The database tracks the synced timestamp in `user_settings.job_templates_schema_timestamp` and `ai_instructions.modified_timestamp`.
  - When the server boots (in `lifespan`) or when a sync is triggered, the system compares the JSON file's `modified_timestamp` against the database.
  - If the timestamp or content differs, it automatically synchronizes the modified schema into the database.
  - Reverse sync endpoints (`/export`) allow exporting database updates back into the JSON files with a fresh timestamp.

* **Database-Driven AI Evaluation**:
  - Before making any LLM API calls (Gemini, Groq, Mistral, OpenRouter), the AI engine queries the database (`ai_instructions` table) for the active RAG prompt template and Bar Raiser system instruction.
  - This allows real-time dynamic customization of prompts and evaluation rubrics without redeploying code.

* **API Endpoints**:
  - `GET /api/v1/settings/schema/defaults`: Returns active templates and system defaults schema.
  - `POST /api/v1/settings/schema/defaults/sync`: Synchronizes `default_job_templates.json` into the database.
  - `POST /api/v1/settings/schema/templates/export`: Exports database templates to `default_job_templates.json`.
  - `GET /api/v1/settings/schema/ai-instructions`: Retrieves active RAG & AI instructions from the database.
  - `PUT /api/v1/settings/schema/ai-instructions`: Updates AI instructions in both database and JSON file.
  - `POST /api/v1/settings/schema/ai-instructions/sync`: Synchronizes `rag_ai_instructions.json` into the database.
  - `POST /api/v1/settings/schema/ai-instructions/export`: Exports database instructions to `rag_ai_instructions.json`.



