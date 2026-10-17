from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    database_url: str = "postgresql://postgres:clearpath@localhost:5432/clearpath"
    ors_api_key: str = ""
    frontend_origin: str = "http://localhost:5173"
    barrier_source: Literal["fixtures", "postgres"] = "fixtures"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    background_refresh: bool = True  # keep live feeds warm in a background thread (off in tests)


settings = Settings()
