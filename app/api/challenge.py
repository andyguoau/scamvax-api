import logging
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import get_settings
from app.core.database import get_db
from app.models.challenge import Challenge
from app.services.tts import generate_ai_audio, TTSVCError
from app.services.audio import convert_to_wav, AudioProcessingError
from app.services import storage

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["challenge"])


# ─── POST /test_upload（仅测试用，验证 R2 上传和公开 URL）────────────────────

@router.post("/test_upload")
async def test_upload(audio: UploadFile = File(...)):
    """上传音频到 R2，返回公开 URL，用于验证 R2 是否正常工作"""
    audio_bytes = await audio.read()
    key = f"test/{uuid.uuid4()}.wav"
    url = storage.upload_raw(key, audio_bytes)
    return JSONResponse({"key": key, "public_url": url})


# ─── POST /create_challenge ──────────────────────────────────────────────────

@router.post("/create_challenge")
async def create_challenge(
    audio: UploadFile = File(..., description="支持 WAV / MP3 / M4A / AAC / OGG / FLAC / WEBM"),
    device_id: str = Form(..., description="设备唯一 ID，由 App 生成并持久化"),
    unlock_proof: str = Form(..., description="解锁凭证：CREDIT / BONUS / IAP_1 / IAP_4"),
    lang: str = Form("zh", description="语言：zh 或 en"),
    db: AsyncSession = Depends(get_db),
):
    """
    接收 App 上传的录音，生成 fake 语音并返回挑战页面 URL。

    流程：
    1. 读取音频 buffer（内存，不落盘）
    2. 自动检测格式并转换为 WAV（支持 m4a/mp3/ogg/flac 等）
    3. 发送到阿里云 TTS-VC API 生成 fake 音频
    4. 生成 challenge_id (UUID)
    5. 上传 fake 音频到 R2: fake/{challenge_id}.wav
    6. 原始音频立即丢弃
    7. 写入 challenges 表
    8. 返回 challenge_url
    """
    # ── 校验解锁凭证 ──
    if not unlock_proof or unlock_proof.upper() == "NONE":
        raise HTTPException(
            status_code=402,
            detail={"error_code": "UNLOCK_REQUIRED", "message": "需要有效的解锁凭证"},
        )

    # ── 设备频率限制 ──
    window_start = datetime.now(timezone.utc) - timedelta(
        seconds=settings.rate_limit_window_seconds
    )
    rate_result = await db.execute(
        select(Challenge).where(
            and_(
                Challenge.device_id == device_id,
                Challenge.created_at >= window_start,
            )
        )
    )
    recent_count = len(rate_result.scalars().all())
    if recent_count >= settings.rate_limit_per_device:
        raise HTTPException(
            status_code=429,
            detail={"error_code": "RATE_LIMITED", "message": "创建频率超限，请稍后再试"},
        )

    # ── 读取音频到内存 buffer，不落盘 ──
    max_bytes = settings.audio_max_size_mb * 1024 * 1024
    audio_bytes = await audio.read()
    if len(audio_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={"error_code": "FILE_TOO_LARGE", "message": f"文件超过 {settings.audio_max_size_mb}MB 限制"},
        )

    # ── 格式转换：统一转成 WAV ──
    try:
        audio_bytes = convert_to_wav(
            audio_bytes,
            filename=audio.filename or "",
            content_type=audio.content_type or "",
        )
    except AudioProcessingError as e:
        raise HTTPException(
            status_code=422,
            detail={"error_code": e.error_code, "message": str(e)},
        )

    # ── 生成 challenge_id ──
    challenge_id = str(uuid.uuid4())

    # ── 调用阿里云 TTS-VC 生成 fake 音频（直接传 bytes，不落盘）──
    try:
        fake_audio = await generate_ai_audio(audio_bytes)
    except TTSVCError as e:
        logger.error(f"TTS-VC 生成失败: {e}")
        raise HTTPException(
            status_code=503,
            detail={"error_code": "MODEL_FAILED", "message": "AI 音频生成失败，请重试"},
        )
    finally:
        del audio_bytes  # 原始音频立即丢弃

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
    challenge = Challenge(id=challenge_id, fake_url=fake_url, device_id=device_id)
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
    h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 16px; line-height: 1.3; }}
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

    /* App download section */
    .app-section {{
      margin-top: 32px; padding-top: 24px;
      border-top: 1px solid #334155; text-align: center;
    }}
    .app-title {{
      font-size: 16px; font-weight: 700; color: #f1f5f9; margin-bottom: 6px;
    }}
    .app-subtitle {{
      font-size: 13px; color: #64748b; margin-bottom: 16px; line-height: 1.5;
    }}
    .store-btns {{
      display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;
    }}
    .store-btn {{
      display: inline-flex; align-items: center; gap: 8px;
      background: #0f172a; border: 1px solid #334155; border-radius: 10px;
      padding: 10px 18px; text-decoration: none; color: #f1f5f9;
      font-size: 14px; font-weight: 600; transition: border-color .2s;
    }}
    .store-btn:hover {{ border-color: #6366f1; }}
    .store-btn svg {{ width: 20px; height: 20px; flex-shrink: 0; }}
  </style>
</head>
<body>
  <div class="card">
    <h1 id="title">Can you trust this voice?</h1>
    <p class="description" id="description">
      This is an AI-cloned voice. Modern AI can replicate anyone's voice from just a few seconds of audio.
      If you received a call like this — would you know it was fake?
    </p>

    <div class="audio-block">
      <audio controls>
        <source src="{fake_url}" type="audio/wav"/>
        Your browser does not support the audio element.
      </audio>
      <div class="audio-label" id="audio-label">AI-generated voice — this is NOT a real person</div>
    </div>

    <a class="share-btn" href="javascript:void(0)" onclick="shareChallenge()" id="share-btn">
      Send this challenge to your family
    </a>

    <div class="app-section">
      <div class="app-title" id="app-title">Create Your Own Voice Challenge</div>
      <div class="app-subtitle" id="app-subtitle">Protect the people you care about from AI voice scams.</div>
      <div class="store-btns">
        <a class="store-btn" href="#" id="ios-btn">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/></svg>
          <span id="ios-label">Download on the App Store</span>
        </a>
        <a class="store-btn" href="#" id="android-btn">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 18.5v-13c0-.83.94-1.3 1.6-.8l13 6.5c.6.3.6 1.3 0 1.6l-13 6.5c-.66.5-1.6.03-1.6-.8z"/></svg>
          <span id="android-label">Get it on Google Play</span>
        </a>
      </div>
    </div>
  </div>

  <script>
    // 根据浏览器语言自动切换中英文
    var lang = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
    var isChinese = lang.startsWith('zh');

    if (isChinese) {{
      document.documentElement.lang = 'zh';
      document.title = '你能听出这是 AI 声音吗？';
      document.getElementById('title').textContent = '你能听出这是 AI 声音吗？';
      document.getElementById('description').textContent =
        '这是一段 AI 克隆的声音。现代 AI 只需几秒录音就能完美复制任何人的声音。如果你接到这样的电话，你能判断出是假的吗？';
      document.getElementById('audio-label').textContent = 'AI 生成的声音 — 这不是真人录音';
      document.getElementById('share-btn').textContent = '把这个挑战发给你的家人';
      document.getElementById('app-title').textContent = '制作你的专属声音挑战';
      document.getElementById('app-subtitle').textContent = '保护你在乎的人，远离 AI 语音诈骗。';
      document.getElementById('ios-label').textContent = 'App Store 下载';
      document.getElementById('android-label').textContent = 'Google Play 下载';
    }}

    function shareChallenge() {{
      var url = window.location.href;
      var isCh = document.documentElement.lang === 'zh';
      var title = isCh ? '你能听出这是 AI 声音吗？' : 'Can you trust this voice?';
      var text = isCh
        ? '听听这段声音，你能分辨出是真人还是 AI 克隆吗？'
        : 'Listen to this AI voice clone — can you tell it\\'s fake? Share with your family to protect them.';
      if (navigator.share) {{
        navigator.share({{ title: title, text: text, url: url }});
      }} else if (navigator.clipboard) {{
        navigator.clipboard.writeText(url).then(function() {{
          alert(isCh ? '链接已复制，快分享给家人！' : 'Challenge link copied! Share it with your family.');
        }});
      }} else {{
        prompt(isCh ? '复制链接，分享给家人：' : 'Copy this link and share it with your family:', url);
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
