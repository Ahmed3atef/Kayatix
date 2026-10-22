import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./kayatix.db"


def read_env_file_variable(var_name: str, env_path: Optional[str] = None) -> Optional[str]:
    """Reads a variable value directly from the .env file if present."""
    target_env = env_path or os.path.join(os.getcwd(), ".env")
    if os.path.isfile(target_env):
        try:
            with open(target_env, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if "=" in stripped:
                        key, val = stripped.split("=", 1)
                        if key.strip() == var_name:
                            cleaned = val.strip().strip("'\"")
                            if cleaned:
                                return cleaned
        except Exception:
            pass
    return None


def resolve_env_variable(
    var_name: str, default: Optional[str] = None, env_path: Optional[str] = None
) -> Optional[str]:
    """
    Resolves configuration variable with strict priority order:
    1. Read from .env file if it exists and defines a non-empty value.
    2. Read from system environment variables (os.environ).
    3. Return default value if neither is set.
    """
    val = read_env_file_variable(var_name, env_path=env_path)
    if val:
        return val
    system_env = os.environ.get(var_name, "").strip().strip("'\"")
    if system_env:
        return system_env
    return default


def resolve_database_url(env_path: Optional[str] = None) -> str:
    """
    Resolves active database URL following strict priority order:
    1. Read DATABASE_URL from .env file if it exists and defines a non-empty value.
    2. If not defined in .env, read from system environment variables (os.environ).
    3. If neither is set, fall back to default SQLite database file ('sqlite+aiosqlite:///./kayatix.db').
    """
    return resolve_env_variable("DATABASE_URL", DEFAULT_SQLITE_URL, env_path=env_path) or DEFAULT_SQLITE_URL


def resolve_admin_credentials(env_path: Optional[str] = None) -> dict:
    """
    Resolves default administrator user credentials following strict priority order:
    1. Read from .env file if it exists and defines non-empty values.
    2. Read from system environment variables (os.environ).
    3. If neither defines credentials, returns None for email & password.
    """
    email = resolve_env_variable("ADMIN_EMAIL", None, env_path) or resolve_env_variable("DEFAULT_ADMIN_EMAIL", None, env_path)
    password = resolve_env_variable("ADMIN_PASSWORD", None, env_path) or resolve_env_variable("DEFAULT_ADMIN_PASSWORD", None, env_path)
    full_name = resolve_env_variable("ADMIN_FULL_NAME", "Platform Administrator", env_path)
    return {
        "email": email,
        "password": password,
        "full_name": full_name or "Platform Administrator",
    }


class Settings(BaseSettings):
    PROJECT_NAME: str = "Kayatix (A.Y.A.T. Engine)"
    VERSION: str = "2.0.0"

    # AI & Cloud OCR Keys
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OLLAMA_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: str = "https://ollama.com/v1"
    LLAMA_CLOUD_API_KEY: Optional[str] = None

    # Google Programmable Search Engine (CSE CX) for Candidate Sourcing
    GOOGLE_CSE_CX_ID: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    DATABASE_URL: str = "sqlite+aiosqlite:///./kayatix.db"

    # Engine & Subscription defaults
    EVALUATION_MODE: str = "llm_cascade"
    SUBSCRIPTION_TIER: str = "standard"
    RATE_LIMIT_RPM: int = 15

    # Default Administrator (strictly configured via .env or system environment)
    ADMIN_EMAIL: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_FULL_NAME: str = "Platform Administrator"

    # Authentication & Session Security
    SECRET_KEY: str = "kayatix-jwt-session-secret-key-32-chars-min"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        if not self.GOOGLE_CSE_ID and self.GOOGLE_CSE_CX_ID:
            self.GOOGLE_CSE_ID = self.GOOGLE_CSE_CX_ID
        elif not self.GOOGLE_CSE_CX_ID and self.GOOGLE_CSE_ID:
            self.GOOGLE_CSE_CX_ID = self.GOOGLE_CSE_ID

        # Apply strict DATABASE_URL resolution order (.env -> os.environ -> SQLite default)
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.DATABASE_URL = resolve_database_url()
        elif not self.DATABASE_URL or self.DATABASE_URL == DEFAULT_SQLITE_URL:
            self.DATABASE_URL = resolve_database_url()

        # Apply strict Admin user resolution order (.env -> os.environ)
        admin_creds = resolve_admin_credentials()
        if admin_creds["email"]:
            self.ADMIN_EMAIL = admin_creds["email"]
        if admin_creds["password"]:
            self.ADMIN_PASSWORD = admin_creds["password"]
        if admin_creds["full_name"]:
            self.ADMIN_FULL_NAME = admin_creds["full_name"]

        # Apply strict SECRET_KEY resolution
        resolved_secret = resolve_env_variable("SECRET_KEY", None)
        if resolved_secret:
            self.SECRET_KEY = resolved_secret



settings = Settings()
