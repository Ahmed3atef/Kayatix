from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()
