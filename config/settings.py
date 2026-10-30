import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    """Application settings loaded from environment or defaults."""
    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'tenantease.db'}"
    LLM_PROVIDER: str = "mock"  # "mock", "openai", or "disabled"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    RANDOM_SEED: int = 42
    RULE_VERSION: str = "v1.2.0"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
