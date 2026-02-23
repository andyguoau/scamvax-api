from fastapi import APIRouter

from app.core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api", tags=["client-config"])


@router.get("/client-config")
async def client_config():
    """客户端远程配置（当前仅包含广告配置）"""
    return {
        "ads": {
            "enabled": settings.ads_enabled,
            "interstitial": {
                "ios": settings.admob_interstitial_ios,
                "android": settings.admob_interstitial_android,
            },
        },
    }
