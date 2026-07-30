from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Default: local peer-auth via Unix socket as OS user (no password)
    database_url: str = "postgresql+psycopg2:///estimating"
    api_title: str = "S&S Estimating API"
    api_version: str = "0.1.0"


settings = Settings()
