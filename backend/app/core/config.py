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

    max_upload_mb: int = 1024  # 视频上传上限（与前端「最大 1GB」一致）

    # ---- Doubao (ByteDance) speech ----
    doubao_tts_url: str = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    doubao_tts_access_key: str = ""
    doubao_tts_app_id: str = ""
    doubao_tts_resource_id: str = "seed-tts-2.0"
    doubao_asr_url: str = (
        "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
    )
    doubao_asr_api_key: str = ""
    doubao_asr_resource_id: str = "volc.seedasr.auc"

    # ---- Doubao LLM (火山方舟 Ark) — AI 写文案 / 文本翻译 ----
    ark_api_key: str = ""
    ark_endpoint: str = "https://ark.cn-beijing.volces.com/api/v3/responses"
    ark_model: str = "doubao-seed-2-0-pro-260215"

    # ---- VoxCPM 语音克隆（自建 GPU 服务，HTTP 调用）----
    # 直连 voxcpm/server.py: http://127.0.0.1:8190
    # 经 ailab 网关:        http://127.0.0.1:8089/tts/voxcpm
    voxcpm_url: str = ""
    voxcpm_timeout: int = 180

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
