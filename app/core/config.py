import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./kayatix.db"


def resolve_database_url(env_path: Optional[str] = None) -> str:
    """
    Resolves active database URL following strict priority order:
    1. Read DATABASE_URL from .env file if it exists and defines a non-empty value.
    2. If not defined in .env, read from system environment variables (os.environ).
    3. If neither is set, fall back to default SQLite database file ('sqlite+aiosqlite:///./kayatix.db').
    """
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
                        if key.strip() == "DATABASE_URL":
                            cleaned = val.strip().strip("'\"")
                            if cleaned:
                                return cleaned
        except Exception:
            pass

    system_env = os.environ.get("DATABASE_URL", "").strip().strip("'\"")
    if system_env:
        return system_env

    return DEFAULT_SQLITE_URL


class Settings(BaseSettings):
    PROJECT_NAME: str = "Kayatix (A.Y.A.T. Engine)"
    VERSION: str = "2.0.0"

    # AI & Cloud OCR Keys
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None
    LLAMA_CLOUD_API_KEY: Optional[str] = None

    # Google X-Ray Search Keys (LinkedIn Legal Sourcing)
    GOOGLE_SEARCH_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None
    GOOGLE_CSE_API_KEY: Optional[str] = None
    GOOGLE_CSE_CX_ID: Optional[str] = None

    DATABASE_URL: str = "sqlite+aiosqlite:///./kayatix.db"

    # Engine & Subscription defaults
    EVALUATION_MODE: str = "llm_cascade"
    SUBSCRIPTION_TIER: str = "standard"
    RATE_LIMIT_RPM: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        # Harmonize Google Search / CSE keys
        if not self.GOOGLE_SEARCH_API_KEY and self.GOOGLE_CSE_API_KEY:
            self.GOOGLE_SEARCH_API_KEY = self.GOOGLE_CSE_API_KEY
        elif not self.GOOGLE_CSE_API_KEY and self.GOOGLE_SEARCH_API_KEY:
            self.GOOGLE_CSE_API_KEY = self.GOOGLE_SEARCH_API_KEY

        if not self.GOOGLE_CSE_ID and self.GOOGLE_CSE_CX_ID:
            self.GOOGLE_CSE_ID = self.GOOGLE_CSE_CX_ID
        elif not self.GOOGLE_CSE_CX_ID and self.GOOGLE_CSE_ID:
            self.GOOGLE_CSE_CX_ID = self.GOOGLE_CSE_ID

        # Apply strict DATABASE_URL resolution order (.env -> os.environ -> SQLite default)
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.DATABASE_URL = resolve_database_url()
        elif not self.DATABASE_URL or self.DATABASE_URL == DEFAULT_SQLITE_URL:
            self.DATABASE_URL = resolve_database_url()


settings = Settings()
