import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.models.challenge import Challenge
from app.services.tts import generate_ai_audio, TTSVCError
from app.services import storage

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["challenge"])


# ─── POST /create_challenge ──────────────────────────────────────────────────

@router.post("/create_challenge")
async def create_challenge(
    audio: UploadFile = File(..., description="WAV PCM16 24kHz Mono"),
    db: AsyncSession = Depends(get_db),
):
    """
    接收 App 上传的录音，生成 fake 语音并返回挑战页面 URL。

    流程：
    1. 读取音频 buffer（内存，不落盘）
    2. 发送到阿里云 TTS-VC API 生成 fake 音频
    3. 生成 challenge_id (UUID)
    4. 上传 fake 音频到 R2: fake/{challenge_id}.wav
    5. 原始音频立即丢弃
    6. 写入 challenges 表
    7. 返回 challenge_url
    """
    # ── 读取音频到内存 buffer，不落盘 ──
    max_bytes = settings.audio_max_size_mb * 1024 * 1024
    audio_bytes = await audio.read()
    if len(audio_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={"error_code": "FILE_TOO_LARGE", "message": f"文件超过 {settings.audio_max_size_mb}MB 限制"},
        )

    # ── 生成 challenge_id ──
    challenge_id = str(uuid.uuid4())

    # ── 先把原始音频临时上传到 R2，获取公开 URL 供 DashScope 访问 ──
    # DashScope 不接受 bytes，只接受公开 HTTPS URL
    temp_key = f"uploads/{challenge_id}_src.wav"
    try:
        source_public_url = storage.upload_raw(temp_key, audio_bytes)
    except Exception as e:
        logger.error(f"原始音频上传失败: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error_code": "STORAGE_FAILED", "message": "音频存储失败，请重试"},
        )
    finally:
        del audio_bytes

    # ── 调用阿里云 TTS-VC 生成 fake 音频 ──
    try:
        fake_audio = await generate_ai_audio(source_public_url)
    except TTSVCError as e:
        logger.error(f"TTS-VC 生成失败: {e}")
        # 清理临时原始音频
        storage.delete_by_key(temp_key)
        raise HTTPException(
            status_code=503,
            detail={"error_code": "MODEL_FAILED", "message": "AI 音频生成失败，请重试"},
        )

    # ── 删除临时原始音频（不保留用户声音）──
    storage.delete_by_key(temp_key)

    # ── 上传 fake 音频到 R2: fake/{challenge_id}.wav ──
    try:
        fake_url = storage.upload_audio(challenge_id, fake_audio)
    except Exception as e:
        logger.error(f"R2 上传失败: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error_code": "STORAGE_FAILED", "message": "音频存储失败，请重试"},
        )
    finally:
        del fake_audio

    # ── 写入数据库 ──
    challenge = Challenge(id=challenge_id, fake_url=fake_url)
    db.add(challenge)
    await db.commit()

    challenge_url = f"{settings.base_url}/c/{challenge_id}"
    logger.info(f"Challenge 创建成功: {challenge_id}")
    return JSONResponse({"challenge_url": challenge_url})


# ─── GET /c/{challenge_id} ───────────────────────────────────────────────────

CHALLENGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Can you trust this voice?</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f172a; color: #f1f5f9; min-height: 100vh;
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; padding: 24px;
    }}
    .card {{
      background: #1e293b; border-radius: 16px; padding: 32px;
      max-width: 480px; width: 100%; box-shadow: 0 25px 50px rgba(0,0,0,.5);
    }}
    .badge {{
      background: #ef4444; color: white; font-size: 12px; font-weight: 700;
      padding: 4px 12px; border-radius: 99px; display: inline-block; margin-bottom: 16px;
    }}
    h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 16px; }}
    .description {{
      color: #94a3b8; line-height: 1.6; margin-bottom: 24px; font-size: 15px;
    }}
    .audio-block {{
      background: #0f172a; border-radius: 12px; padding: 24px;
      text-align: center; margin-bottom: 24px;
    }}
    audio {{ width: 100%; margin-bottom: 8px; }}
    .audio-label {{ color: #64748b; font-size: 13px; }}
    .share-btn {{
      display: block; width: 100%; padding: 14px;
      background: #6366f1; color: white; border: none;
      border-radius: 8px; font-size: 16px; font-weight: 600;
      cursor: pointer; text-align: center; text-decoration: none;
      transition: background .2s;
    }}
    .share-btn:hover {{ background: #4f46e5; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #475569; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">Scam Awareness</span>
    <h1>Can you trust this voice?</h1>
    <p class="description">
      This is an AI-cloned voice. Modern AI can perfectly replicate anyone's voice from just a few seconds of audio.
      If you received a call like this asking for money or personal info — would you know it was fake?
    </p>

    <div class="audio-block">
      <audio controls>
        <source src="{fake_url}" type="audio/wav"/>
        Your browser does not support the audio element.
      </audio>
      <div class="audio-label">AI-generated voice — this is NOT a real person</div>
    </div>

    <a class="share-btn" href="javascript:void(0)" onclick="shareChallenge()">
      Send this challenge to your family
    </a>

    <div class="footer">
      Protect your family from voice scams &mdash; ScamVax
    </div>
  </div>

  <script>
    function shareChallenge() {{
      var url = window.location.href;
      if (navigator.share) {{
        navigator.share({{
          title: 'Can you trust this voice?',
          text: 'Listen to this AI voice clone and see if you can tell it\\'s fake. Share with your family to help protect them from voice scams.',
          url: url,
        }});
      }} else if (navigator.clipboard) {{
        navigator.clipboard.writeText(url).then(function() {{
          alert('Challenge link copied! Share it with your family.');
        }});
      }} else {{
        prompt('Copy this link and share it with your family:', url);
      }}
    }}
  </script>
</body>
</html>"""


@router.get("/c/{challenge_id}", response_class=HTMLResponse)
async def challenge_page(
    challenge_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    挑战网页：查询数据库获取 fake_url，返回包含音频播放器的 HTML 页面。
    页面无动态逻辑，仅播放 fake 音频。
    """
    result = await db.execute(
        select(Challenge).where(Challenge.id == challenge_id)
    )
    challenge = result.scalars().first()

    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    html = CHALLENGE_HTML.format(fake_url=challenge.fake_url)
    return HTMLResponse(content=html)
