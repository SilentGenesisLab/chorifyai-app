from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # When True, AI endpoints return mocked results instead of calling
    # real providers (Seedance / TTS / digital-human / LLM).
    mock_mode: bool = True

    # Comma-separated list of allowed CORS origins.
    cors_origins: str = "http://localhost:3001,http://127.0.0.1:3001"

    redis_url: str = "redis://localhost:6379"
    database_url: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
