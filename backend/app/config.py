from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    database_url: str = "postgresql://postgres:clearpath@localhost:5432/clearpath"
    ors_api_key: str = ""
    # Public ORS by default; point at a local server (http://ors:8082/ors/v2 in Docker) when it's down.
    ors_base_url: str = "https://api.heigit.org/openrouteservice/v2"
    frontend_origin: str = "http://localhost:5173"
    barrier_source: Literal["fixtures", "postgres"] = "fixtures"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # When ORS walking or wheelchair routing times out or errors, retry on this profile for a few
    # minutes. Empty turns the fallback off; ors_force_fallback uses it for every request.
    ors_fallback_profile: str = "foot-hiking"
    ors_force_fallback: bool = False
    background_refresh: bool = True  # keep live feeds warm in a background thread (off in tests)


settings = Settings()
