from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    base_url: str = "https://api.scamvax.com"
    secret_key: str = "changeme"

    # Database
    database_url: str

    # Cloudflare R2
    r2_endpoint_url: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str = "scamvax"

    # DashScope — Qwen TTS-VC
    dashscope_api_key: str
    voice_enroll_model: str = "qwen-voice-enrollment"
    tts_model: str = "qwen3-tts-vc-realtime-2026-01-15"
    dashscope_base_http: str = "https://dashscope-intl.aliyuncs.com/api/v1"
    dashscope_base_ws: str = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"

    # Rate limiting
    rate_limit_per_device: int = 5
    rate_limit_window_seconds: int = 3600

    # Audio constraints
    audio_max_size_mb: int = 10
    audio_min_duration_s: float = 10.0
    audio_max_duration_s: float = 20.0

    # Share lifecycle
    share_ttl_hours: int = 72
    share_max_clicks: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
