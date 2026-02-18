import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.services.audio import convert_to_wav, AudioProcessingError
from app.services.tts import generate_ai_audio, TTSVCError
from app.services import share as share_service
from app.services import storage

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/share", tags=["share"])


# ─── 响应模型 ─────────────────────────────────────────────────────────────────

class CreateShareResponse(BaseModel):
    share_id: str
    share_url: str
    expires_at: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str


# ─── POST /api/share/create ──────────────────────────────────────────────────

@router.post("/create", response_model=CreateShareResponse)
async def create_share(
    audio_file: UploadFile = File(..., description="WAV PCM16 24kHz Mono"),
    device_id: str = Form(...),
    unlock_proof: str = Form(..., description="IAP receipt 或 reward token"),
    lang: str = Form("zh"),
    db: AsyncSession = Depends(get_db),
):
    """
    创建挑战 Share：
    1. 校验 unlock_proof（IAP / 奖励次数）
    2. 频率限制检查
    3. 音频校验 + 处理
    4. 调用 TTS-VC 生成 AI 音频
    5. 存储 + 写 DB
    """
    # ── 文件大小检查 ──
    max_bytes = settings.audio_max_size_mb * 1024 * 1024
    contents = await audio_file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={"error_code": "FILE_TOO_LARGE", "message": f"文件超过 {settings.audio_max_size_mb}MB 限制"},
        )

    # ── 频率限制 ──
    allowed = await share_service.check_rate_limit(db, device_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error_code": "RATE_LIMITED", "message": "创建频率超限，请稍后再试"},
        )

    # ── unlock_proof 校验（TODO: 接入真实 IAP 验证）──
    if not unlock_proof or unlock_proof == "NONE":
        raise HTTPException(
            status_code=402,
            detail={"error_code": "UNLOCK_REQUIRED", "message": "需要付费或完成关卡解锁"},
        )

    # ── 音频处理 ──
    try:
        processed_audio = convert_to_wav(
            contents,
            filename=audio_file.filename or "",
            content_type=audio_file.content_type or "",
        )
    except AudioProcessingError as e:
        raise HTTPException(
            status_code=422,
            detail={"error_code": e.error_code, "message": str(e)},
        )

    # ── TTS-VC 生成 AI 音频 ──
    try:
        ai_audio = await generate_ai_audio(processed_audio, lang=lang)
    except TTSVCError as e:
        logger.error(f"TTS-VC 生成失败: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error_code": "MODEL_FAILED", "message": "AI 音频生成失败，请重试"},
        )

    # ── 创建 Share ──
    share = await share_service.create_share(
        db=db,
        device_id=device_id,
        ai_audio_bytes=ai_audio,
        lang=lang,
    )

    share_url = f"{settings.base_url}/s/{share.share_id}"
    return CreateShareResponse(
        share_id=share.share_id,
        share_url=share_url,
        expires_at=share.expires_at.isoformat(),
    )


# ─── GET /api/share/{share_id}/audio ────────────────────────────────────────

@router.get("/{share_id}/audio")
async def get_audio(
    share_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    受控音频播放接口（不暴露 R2 直链）
    仅在 share 为 active 且未过期时返回音频流
    """
    share = await share_service.get_share(db, share_id)

    if share is None or not share.is_accessible():
        raise HTTPException(
            status_code=404,
            detail={"error_code": "SHARE_UNAVAILABLE", "message": "挑战已过期或不存在"},
        )

    try:
        audio_stream = storage.stream_audio(share_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error_code": "AUDIO_NOT_FOUND", "message": "音频不存在"})

    return StreamingResponse(
        audio_stream,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f'inline; filename="challenge_{share_id}.wav"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
