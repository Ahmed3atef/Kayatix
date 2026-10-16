# Database Configuration & Security Architecture

Kayatix supports dual database backends: embedded **SQLite** for local development and cloud **PostgreSQL** (Neon, Supabase, AWS RDS, Docker) for production deployments.

---

## 🔐 Strict Resolution Hierarchy

To maintain bulletproof security and environment stability, `DATABASE_URL` is resolved on the server using a strict 3-tier priority order:

```mermaid
flowchart TD
    A["Server Startup / App Init"] --> B{".env file contains non-empty DATABASE_URL?"}
    B -- Yes --> C["Use DATABASE_URL from .env"]
    B -- No --> D{"System os.environ contains DATABASE_URL?"}
    D -- Yes --> E["Use DATABASE_URL from os.environ"]
    D -- No --> F["Fallback to default SQLite: sqlite+aiosqlite:///./hr_copilot.db"]
    C --> G["Normalize URL & Create AsyncEngine"]
    E --> G
    F --> G
```

1. **Tier 1 — `.env` File (Highest Priority)**:
   The application first checks for a `.env` file in the project root. If `DATABASE_URL` is set, it takes precedence.
2. **Tier 2 — System Environment Variables**:
   If not defined in `.env`, the engine checks standard system environment variables (`os.environ["DATABASE_URL"]`).
3. **Tier 3 — Embedded SQLite Fallback**:
   If neither source defines a connection string, Kayatix automatically initializes a local embedded database at `sqlite+aiosqlite:///./hr_copilot.db` with zero external dependencies.

---

## 🛡️ Enterprise Credential Protection

Database connection strings containing user credentials and passwords are strictly protected:
* **Password Masking**: All connection strings displayed in the user interface, logs, or API responses are sanitized:
  ```text
  postgresql://kaya_db_owner:••••••••@ep-billowing-voice-b5etyv61-pooler.c-7.us-east-2.aws.neon.tech/kaya_db?sslmode=require&channel_binding=require
  ```
* **Browser Network Protection**: The raw database password is **never** streamed over HTTP to the frontend or visible in the browser network tab.
* **Server-Only Management**: Database connections cannot be arbitrarily mutated from the public UI. The deprecated raw configuration editor has been eliminated to prevent credential exfiltration.

---

## 🔌 Supported Database Engines

### 1. Embedded SQLite (Default)
* **URI Format**: `sqlite+aiosqlite:///./hr_copilot.db`
* **Features**: Zero setup, completely offline, ideal for local testing.
* **Storage**: Stored locally in your project root as `hr_copilot.db`.

### 2. Cloud PostgreSQL (Neon / Supabase / AWS RDS / Docker)
* **URI Format**:
  ```text
  postgresql://user:password@host/dbname?sslmode=require&channel_binding=require
  ```
* **Supported Cloud Providers**:
  - **Neon PostgreSQL**: Native support for Neon transaction poolers (`-pooler`).
  - **Supabase**: Direct connection strings or Transaction Pooler links.
  - **AWS RDS / Aurora**: Standard PostgreSQL links with SSL.
  - **Local / Docker Postgres**: `postgresql://postgres:secret@localhost:5432/kaya_db`

---

## ⚡ Automatic URL Normalization & Connection Resilience

Kayatix automatically sanitizes and optimizes database connections:
1. **Driver Mapping**: Maps `postgresql://` and `postgres://` to `postgresql+asyncpg://`.
2. **SSL Compatibility**: Converts `sslmode=require` to `ssl=require` for `asyncpg`.
3. **Parameter Filtering**: Strips unsupported libpq parameters such as `channel_binding=require`.
4. **Pool Pre-Ping (`pool_pre_ping=True`)**: Emits a lightweight ping on connection checkout. If Neon or Supabase severed an idle TCP socket, the dead connection is transparently replaced without raising `InterfaceError: connection is closed`.
5. **Connection Recycling (`pool_recycle=300`)**: Refreshes idle connections every 5 minutes.
6. **Pooler Desync Protection (`statement_cache_size=0`)**: Automatically disables prepared statement caching when connecting through PgBouncer, Neon poolers, or Supabase transaction poolers.
7. **Self-Healing Migrations**: Automatically verifies and creates required tables and columns on startup.


