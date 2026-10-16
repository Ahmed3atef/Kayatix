# Database Configuration & Switching

Kayatix supports dual database backends: embedded **SQLite** for local single-user development, and cloud **PostgreSQL** (Neon, Supabase, AWS RDS, Docker) for production deployments.

---

## 🔌 Supported Database Engines

### 1. Embedded SQLite (Default)
* **URI Format**: `sqlite+aiosqlite:///./hr_copilot.db`
* **Features**: Zero setup, completely offline, zero cloud network dependencies.
* **Storage**: Stored locally in your project root as `hr_copilot.db`.

### 2. Cloud PostgreSQL (Neon / Supabase / AWS RDS / Docker)
* **URI Format**:
  ```text
  postgresql://user:password@host/dbname?sslmode=require&channel_binding=require
  ```
* **Supported Cloud Providers**:
  - **Neon PostgreSQL**: Directly accepts connection strings copied from the Neon Console.
  - **Supabase**: Direct connection strings or Transaction Pooler links.
  - **AWS RDS / Aurora**: Standard PostgreSQL links with SSL.
  - **Local / Docker Postgres**: `postgresql://postgres:secret@localhost:5432/kaya_db`

---

## ⚡ Automatic URL Normalization

Kayatix automatically sanitizes and adapts your database connection string for asynchronous SQLAlchemy with `asyncpg`:
1. Maps `postgresql://` and `postgres://` to `postgresql+asyncpg://`.
2. Converts `sslmode=require` to `ssl=require` (the syntax required by `asyncpg`).
3. Strips unsupported libpq parameters such as `channel_binding=require`.
4. Normalizes SQLite URLs to `sqlite+aiosqlite:///`.

---

## 🔄 Live Switching via Settings

You can switch database backends at runtime directly in the **Settings** page:
1. Navigate to `/settings`.
2. Scroll to the **Database Engine Backend** card.
3. Paste your target connection string in the **Database Connection String** field.
4. Click **Test Connection** to verify latency and tables.
5. Click **Save to Database**.

### Safe Zero-Copy Migration Guarantee:
* The active engine is switched cleanly in memory.
* Missing tables and columns (`database_url`, `evaluation_mode`) are automatically created via self-healing migrations.
* Your current active credentials and default job templates are safely seeded into the new database.
* The old database file on disk is **never** copied or corrupted.
* The new `DATABASE_URL` is persisted to `.env` for subsequent process restarts.

