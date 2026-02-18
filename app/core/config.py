import os
from functools import lru_cache


class Settings:
    def __init__(self):
        # App
        self.app_env = os.environ.get("APP_ENV", "development")
        self.base_url = os.environ.get("BASE_URL", "https://scamvax-api.onrender.com")
        self.secret_key = os.environ.get("SECRET_KEY", "changeme")

        # Database
        self.database_url = os.environ.get("DATABASE_URL", "")

        # Cloudflare R2
        self.r2_endpoint_url = os.environ.get("R2_ENDPOINT_URL", "") or os.environ.get("R2_ENDPOINT", "")
        self.r2_access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "") or os.environ.get("R2_ACCESS_KEY", "")
        self.r2_secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "") or os.environ.get("R2_SECRET_KEY", "")
        self.r2_bucket_name = os.environ.get("R2_BUCKET_NAME", "") or os.environ.get("R2_BUCKET", "scamvax-audio")
        # R2 公开访问 base URL（用于 DashScope voice enrollment）
        self.r2_public_base_url = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")

        # Aliyun / DashScope TTS-VC
        self.dashscope_api_key = os.environ.get("DASHSCOPE_API_KEY", "") or os.environ.get("ALIYUN_API_KEY", "")
        self.aliyun_url = os.environ.get("ALIYUN_URL", "")

        self.voice_enroll_model = os.environ.get("VOICE_ENROLL_MODEL", "qwen-voice-enrollment")
        self.tts_model = os.environ.get("TTS_MODEL", "qwen3-tts-vc-realtime-2026-01-15")
        self.dashscope_base_http = os.environ.get("DASHSCOPE_BASE_HTTP", "https://dashscope-intl.aliyuncs.com/api/v1")
        self.dashscope_base_ws = os.environ.get("DASHSCOPE_BASE_WS", "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime")

        # Rate limiting
        self.rate_limit_per_device = int(os.environ.get("RATE_LIMIT_PER_DEVICE", "5"))
        self.rate_limit_window_seconds = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "3600"))

        # Audio constraints
        self.audio_max_size_mb = int(os.environ.get("AUDIO_MAX_SIZE_MB", "10"))
        self.audio_min_duration_s = float(os.environ.get("AUDIO_MIN_DURATION_S", "10.0"))
        self.audio_max_duration_s = float(os.environ.get("AUDIO_MAX_DURATION_S", "20.0"))

        # Share lifecycle
        self.share_ttl_hours = int(os.environ.get("SHARE_TTL_HOURS", "72"))
        self.share_max_clicks = int(os.environ.get("SHARE_MAX_CLICKS", "50"))

    def get_r2_endpoint(self) -> str:
        return self.r2_endpoint_url

    def get_r2_access_key(self) -> str:
        return self.r2_access_key_id

    def get_r2_secret_key(self) -> str:
        return self.r2_secret_access_key

    def get_r2_bucket(self) -> str:
        return self.r2_bucket_name or "scamvax-audio"

    def get_aliyun_api_key(self) -> str:
        return self.dashscope_api_key


@lru_cache()
def get_settings() -> Settings:
    return Settings()
