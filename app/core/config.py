from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI HR Copilot & Talent Intelligence API"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = "sqlite+aiosqlite:///./hr_copilot.db"

    # AI Provider Keys
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None

    # Legal LinkedIn X-Ray Search Keys
    GOOGLE_CSE_API_KEY: Optional[str] = None
    GOOGLE_CSE_CX_ID: Optional[str] = None

    # Engine & Subscription defaults
    EVALUATION_MODE: str = "hybrid"  # "hybrid", "llm_cascade", "local_offline"
    SUBSCRIPTION_TIER: str = "standard"
    RATE_LIMIT_RPM: int = 15

    model_config = SettingsConfigDict(
        extra="ignore"
    )


settings = Settings()
