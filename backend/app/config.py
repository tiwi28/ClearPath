from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str = "postgresql://postgres:clearpath@localhost:5432/clearpath"
    gemini_api_key: str = ""
    ors_api_key: str = ""
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
