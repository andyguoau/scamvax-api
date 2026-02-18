from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    base_url: str = "https://api.scamvax.com"
    secret_key: str = "changeme"

    # Database
    database_url: str

    # Cloudflare R2
    # 支持两套命名：r2_endpoint_url 或 r2_endpoint
    r2_endpoint_url: str = ""
    r2_endpoint: str = ""          # 别名（指令要求的 R2_ENDPOINT）
    r2_access_key_id: str = ""
    r2_access_key: str = ""        # 别名（指令要求的 R2_ACCESS_KEY）
    r2_secret_access_key: str = ""
    r2_secret_key: str = ""        # 别名（指令要求的 R2_SECRET_KEY）
    r2_bucket_name: str = "scamvax-audio"
    r2_bucket: str = ""            # 别名（指令要求的 R2_BUCKET）

    # DashScope / Aliyun TTS-VC
    # 支持两套命名：dashscope_api_key 或 aliyun_api_key
    dashscope_api_key: str = ""
    aliyun_api_key: str = ""       # 别名（指令要求的 ALIYUN_API_KEY）
    aliyun_url: str = ""           # 阿里云 API 端点（指令要求的 ALIYUN_URL）

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

    def get_r2_endpoint(self) -> str:
        return self.r2_endpoint_url or self.r2_endpoint

    def get_r2_access_key(self) -> str:
        return self.r2_access_key_id or self.r2_access_key

    def get_r2_secret_key(self) -> str:
        return self.r2_secret_access_key or self.r2_secret_key

    def get_r2_bucket(self) -> str:
        return self.r2_bucket_name or self.r2_bucket or "scamvax-audio"

    def get_aliyun_api_key(self) -> str:
        return self.dashscope_api_key or self.aliyun_api_key


@lru_cache()
def get_settings() -> Settings:
    return Settings()
