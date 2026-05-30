from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # When True, AI generation returns mocked results (no real provider calls).
    mock_mode: bool = True

    # Comma-separated allowed CORS origins (frontend dev server).
    cors_origins: str = "http://localhost:3001,http://127.0.0.1:3001"

    # ---- Aliyun OSS (real file storage) ----
    oss_provider: str = "aliyun"  # "aliyun" | "mock"
    aliyun_oss_endpoint: str = "oss-cn-shenzhen.aliyuncs.com"
    aliyun_oss_bucket: str = "chorify-nova"
    aliyun_oss_access_key_id: str = ""
    aliyun_oss_access_key_secret: str = ""
    aliyun_oss_public_base_url: str = "https://oss3.sligenai.cn"

    max_upload_mb: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
