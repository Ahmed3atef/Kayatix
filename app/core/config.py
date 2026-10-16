import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./hr_copilot.db"


def resolve_database_url(env_path: Optional[str] = None) -> str:
    """
    Resolves active database URL following strict priority order:
    1. Read DATABASE_URL from .env file if it exists and defines a non-empty value.
    2. If not defined in .env, read from system environment variables (os.environ).
    3. If neither is set, fall back to default SQLite database file ('sqlite+aiosqlite:///./hr_copilot.db').
    """
    # 1. First priority: Check .env file directly
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

    # 2. Second priority: System environment variables
    system_env = os.environ.get("DATABASE_URL", "").strip().strip("'\"")
    if system_env:
        return system_env

    # 3. Third priority: Fall back to default SQLite database file
    return DEFAULT_SQLITE_URL


class Settings(BaseSettings):
    PROJECT_NAME: str = "Kayatix - A.Y.A.T. Engine"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = ""

    # AI Provider Keys
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None

    # Legal LinkedIn X-Ray Search Keys
    GOOGLE_CSE_API_KEY: Optional[str] = None
    GOOGLE_CSE_CX_ID: Optional[str] = None

    # Engine & Subscription defaults
    EVALUATION_MODE: str = "llm_cascade"
    SUBSCRIPTION_TIER: str = "standard"
    RATE_LIMIT_RPM: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        # Apply strict DATABASE_URL resolution order (.env -> os.environ -> SQLite default)
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.DATABASE_URL = resolve_database_url()
        elif not self.DATABASE_URL:
            self.DATABASE_URL = resolve_database_url()


settings = Settings()

