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
    challenge = Challenge(id=challenge_id, fake_url=fake_url)
    db.add(challenge)
    await db.commit()

    challenge_url = f"{settings.base_url}/c/{challenge_id}"
    logger.info(f"Challenge 创建成功: {challenge_id}")
    return JSONResponse({"challenge_url": challenge_url})


# ─── GET /c/{challenge_id} ───────────────────────────────────────────────────

CHALLENGE_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0"/>
  <title>10秒听声挑战 · ScamVax</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}}
    :root{{
      --bg:#0a0f1e;
      --card:#131929;
      --card2:#1a2236;
      --accent:#6366f1;
      --accent2:#818cf8;
      --danger:#ef4444;
      --success:#22c55e;
      --text:#f1f5f9;
      --muted:#64748b;
      --border:#1e2d45;
    }}
    html,body{{height:100%;}}
    body{{
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      background:var(--bg);color:var(--text);
      min-height:100vh;display:flex;flex-direction:column;
      align-items:center;justify-content:flex-start;
      padding:20px 16px 40px;
    }}

    /* ── Step indicator ── */
    .steps{{
      display:flex;align-items:center;gap:8px;
      margin-bottom:24px;margin-top:8px;
    }}
    .step{{
      width:28px;height:28px;border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      font-size:12px;font-weight:700;
      border:2px solid var(--border);color:var(--muted);
      transition:all .3s;
    }}
    .step.active{{border-color:var(--accent);color:var(--accent);background:rgba(99,102,241,.12);}}
    .step.done{{border-color:var(--success);color:var(--success);background:rgba(34,197,94,.12);}}
    .step-line{{flex:1;height:2px;background:var(--border);border-radius:1px;transition:background .3s;}}
    .step-line.done{{background:var(--success);}}

    /* ── Card ── */
    .card{{
      width:100%;max-width:440px;
      background:var(--card);border-radius:20px;
      border:1px solid var(--border);
      padding:28px 24px;
      box-shadow:0 32px 64px rgba(0,0,0,.5);
    }}

    /* ── Phase 1: Listen ── */
    #phase-listen{{display:block;}}
    .challenge-label{{
      font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
      color:var(--accent2);margin-bottom:12px;
    }}
    .challenge-title{{
      font-size:26px;font-weight:800;line-height:1.2;
      margin-bottom:6px;
    }}
    .challenge-sub{{
      font-size:15px;color:var(--muted);line-height:1.5;
      margin-bottom:28px;
    }}

    /* big play button */
    .play-wrap{{
      display:flex;flex-direction:column;align-items:center;
      gap:16px;margin-bottom:28px;
    }}
    .play-btn{{
      width:100px;height:100px;border-radius:50%;
      background:linear-gradient(135deg,var(--accent),#4f46e5);
      border:none;cursor:pointer;
      display:flex;align-items:center;justify-content:center;
      box-shadow:0 0 0 0 rgba(99,102,241,.4);
      transition:transform .15s,box-shadow .15s;
      position:relative;
    }}
    .play-btn:hover{{transform:scale(1.06);}}
    .play-btn:active{{transform:scale(.96);}}
    .play-btn.playing{{
      animation:pulse 1.8s infinite;
    }}
    @keyframes pulse{{
      0%{{box-shadow:0 0 0 0 rgba(99,102,241,.5);}}
      70%{{box-shadow:0 0 0 20px rgba(99,102,241,0);}}
      100%{{box-shadow:0 0 0 0 rgba(99,102,241,0);}}
    }}
    .play-icon{{font-size:36px;line-height:1;color:#fff;margin-left:4px;}}
    .pause-icon{{font-size:32px;line-height:1;color:#fff;display:none;}}
    .play-btn.playing .play-icon{{display:none;}}
    .play-btn.playing .pause-icon{{display:block;}}

    .play-status{{
      font-size:14px;color:var(--muted);text-align:center;min-height:20px;
    }}

    /* waveform bars */
    .waveform{{
      display:flex;align-items:center;justify-content:center;
      gap:3px;height:32px;opacity:0;transition:opacity .3s;
    }}
    .waveform.active{{opacity:1;}}
    .bar{{
      width:4px;border-radius:2px;background:var(--accent);
      animation:wave 1s ease-in-out infinite;
    }}
    .bar:nth-child(1){{height:8px;animation-delay:0s;}}
    .bar:nth-child(2){{height:18px;animation-delay:.1s;}}
    .bar:nth-child(3){{height:26px;animation-delay:.2s;}}
    .bar:nth-child(4){{height:14px;animation-delay:.3s;}}
    .bar:nth-child(5){{height:22px;animation-delay:.4s;}}
    .bar:nth-child(6){{height:10px;animation-delay:.5s;}}
    .bar:nth-child(7){{height:20px;animation-delay:.15s;}}
    .bar:nth-child(8){{height:16px;animation-delay:.35s;}}
    @keyframes wave{{
      0%,100%{{transform:scaleY(1);}}
      50%{{transform:scaleY(.3);}}
    }}

    /* answer prompt */
    .answer-prompt{{
      text-align:center;padding:14px;
      border-radius:12px;background:var(--card2);
      font-size:14px;color:var(--muted);
      transition:all .3s;
    }}
    .answer-prompt.ready{{
      color:var(--text);
      background:linear-gradient(135deg,rgba(99,102,241,.2),rgba(79,70,229,.1));
      border:1px solid rgba(99,102,241,.3);
    }}

    /* ── Phase 2: Guess ── */
    #phase-guess{{display:none;}}
    .guess-title{{
      font-size:20px;font-weight:700;text-align:center;
      margin-bottom:8px;
    }}
    .guess-sub{{
      font-size:14px;color:var(--muted);text-align:center;
      margin-bottom:24px;
    }}
    .choices{{display:flex;gap:12px;}}
    .choice-btn{{
      flex:1;padding:20px 12px;border-radius:16px;
      border:2px solid var(--border);background:var(--card2);
      color:var(--text);cursor:pointer;
      display:flex;flex-direction:column;align-items:center;gap:8px;
      font-size:15px;font-weight:600;
      transition:all .2s;
    }}
    .choice-btn:hover{{border-color:var(--accent);background:rgba(99,102,241,.08);transform:translateY(-2px);}}
    .choice-btn:active{{transform:scale(.97);}}
    .choice-icon{{font-size:32px;}}

    /* ── Phase 3: Reveal ── */
    #phase-reveal{{display:none;}}
    .reveal-header{{
      text-align:center;padding:20px;
      border-radius:16px;margin-bottom:20px;
    }}
    .reveal-header.wrong{{
      background:linear-gradient(135deg,rgba(239,68,68,.15),rgba(239,68,68,.05));
      border:1px solid rgba(239,68,68,.3);
    }}
    .reveal-header.right{{
      background:linear-gradient(135deg,rgba(34,197,94,.15),rgba(34,197,94,.05));
      border:1px solid rgba(34,197,94,.3);
    }}
    .reveal-emoji{{font-size:48px;margin-bottom:10px;}}
    .reveal-verdict{{font-size:22px;font-weight:800;line-height:1.3;margin-bottom:8px;}}
    .reveal-verdict.wrong{{color:var(--danger);}}
    .reveal-verdict.right{{color:var(--success);}}
    .reveal-note{{font-size:14px;color:var(--muted);line-height:1.5;}}

    /* tip box */
    .tip-box{{
      background:var(--card2);border-radius:14px;
      border-left:3px solid var(--accent);
      padding:14px 16px;margin-bottom:20px;
    }}
    .tip-label{{
      font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
      color:var(--accent2);margin-bottom:6px;
    }}
    .tip-text{{font-size:14px;line-height:1.6;color:#cbd5e1;}}

    /* replay small */
    .replay-row{{
      display:flex;align-items:center;justify-content:center;
      gap:10px;margin-bottom:20px;
    }}
    .replay-btn{{
      display:flex;align-items:center;gap:6px;
      background:none;border:1px solid var(--border);
      color:var(--muted);border-radius:8px;padding:8px 16px;
      font-size:13px;cursor:pointer;transition:all .2s;
    }}
    .replay-btn:hover{{border-color:var(--accent);color:var(--accent2);}}

    /* CTA section */
    .cta-label{{
      font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
      color:var(--muted);text-align:center;margin-bottom:12px;
    }}
    .cta-main{{
      display:flex;align-items:center;justify-content:center;
      width:100%;padding:16px 20px;
      background:linear-gradient(135deg,var(--accent),#4f46e5);
      color:#fff;border:none;border-radius:14px;
      font-size:16px;font-weight:700;
      cursor:pointer;text-decoration:none;
      gap:8px;transition:all .2s;
      box-shadow:0 4px 20px rgba(99,102,241,.35);
      margin-bottom:12px;
    }}
    .cta-main:hover{{transform:translateY(-1px);box-shadow:0 6px 28px rgba(99,102,241,.5);}}
    .cta-main:active{{transform:scale(.98);}}
    .cta-arrow{{font-size:18px;}}

    .store-row{{
      display:flex;gap:10px;justify-content:center;
      margin-bottom:20px;
    }}
    .store-btn{{
      flex:1;max-width:160px;
      display:flex;align-items:center;justify-content:center;gap:8px;
      padding:10px 14px;border-radius:12px;
      border:1px solid var(--border);background:var(--card2);
      color:var(--text);text-decoration:none;
      font-size:13px;font-weight:600;
      transition:all .2s;
    }}
    .store-btn:hover{{border-color:var(--accent);background:rgba(99,102,241,.08);}}
    .store-icon{{font-size:20px;}}

    /* share row */
    .share-row{{
      display:flex;align-items:center;justify-content:center;gap:8px;
    }}
    .share-small{{
      display:flex;align-items:center;gap:6px;
      background:none;border:1px solid var(--border);
      color:var(--muted);border-radius:8px;padding:10px 18px;
      font-size:13px;font-weight:600;cursor:pointer;
      transition:all .2s;text-decoration:none;
    }}
    .share-small:hover{{border-color:var(--accent2);color:var(--accent2);}}

    .footer{{
      margin-top:24px;font-size:12px;color:var(--muted);text-align:center;
    }}

    /* hidden audio */
    #hidden-audio{{display:none;}}

    /* fade-in animation */
    .fade-in{{animation:fadeIn .4s ease;}}
    @keyframes fadeIn{{from{{opacity:0;transform:translateY(10px);}}to{{opacity:1;transform:translateY(0);}}}}
  </style>
</head>
<body>

  <!-- Step indicator -->
  <div class="steps">
    <div class="step active" id="s1">1</div>
    <div class="step-line" id="sl1"></div>
    <div class="step" id="s2">2</div>
    <div class="step-line" id="sl2"></div>
    <div class="step" id="s3">3</div>
  </div>

  <div class="card">

    <!-- ── PHASE 1: LISTEN ── -->
    <div id="phase-listen">
      <div class="challenge-label">🎮 声音挑战 · Voice Challenge</div>
      <div class="challenge-title">10秒听声挑战</div>
      <div class="challenge-sub">先听再猜：这段声音是真人还是 AI？<br><span style="font-size:13px;opacity:.7;">Listen first. Then guess: Real or AI?</span></div>

      <div class="play-wrap">
        <button class="play-btn" id="playBtn" onclick="togglePlay()">
          <span class="play-icon">▶</span>
          <span class="pause-icon">⏸</span>
        </button>
        <div class="waveform" id="waveform">
          <div class="bar"></div><div class="bar"></div><div class="bar"></div>
          <div class="bar"></div><div class="bar"></div><div class="bar"></div>
          <div class="bar"></div><div class="bar"></div>
        </div>
        <div class="play-status" id="playStatus">点击播放 · Tap to play</div>
      </div>

      <div class="answer-prompt" id="answerPrompt">
        听完才能作答 · Finish listening to answer
      </div>
    </div>

    <!-- ── PHASE 2: GUESS ── -->
    <div id="phase-guess" class="fade-in">
      <div class="guess-title">你的判断？· Your guess?</div>
      <div class="guess-sub">这段声音是——</div>
      <div class="choices">
        <button class="choice-btn" onclick="makeGuess('real')">
          <span class="choice-icon">👤</span>
          <span>真人</span>
          <span style="font-size:12px;color:var(--muted);">Real person</span>
        </button>
        <button class="choice-btn" onclick="makeGuess('ai')">
          <span class="choice-icon">🤖</span>
          <span>AI 生成</span>
          <span style="font-size:12px;color:var(--muted);">AI-generated</span>
        </button>
      </div>
    </div>

    <!-- ── PHASE 3: REVEAL ── -->
    <div id="phase-reveal" class="fade-in">

      <div class="reveal-header" id="revealHeader">
        <div class="reveal-emoji" id="revealEmoji"></div>
        <div class="reveal-verdict" id="revealVerdict"></div>
        <div class="reveal-note" id="revealNote"></div>
      </div>

      <div class="tip-box">
        <div class="tip-label">🛡️ 防骗规则 · Safety Rule</div>
        <div class="tip-text" id="tipText">
          收到家人的紧急求助电话时，先挂断，再用已知的号码主动回拨确认。<br>
          <span style="opacity:.7;">If a family member calls urgently asking for money, hang up and call them back on a number you already know.</span>
        </div>
      </div>

      <div class="replay-row">
        <button class="replay-btn" onclick="replayAudio()">🔁 再听一遍 · Replay</button>
      </div>

      <div class="cta-label">下一步：做你自己的语音挑战 · Create your own</div>

      <a href="#" class="cta-main" id="ctaMain">
        <span>制作我的声音克隆挑战</span>
        <span class="cta-arrow">→</span>
      </a>

      <div class="store-row">
        <a href="#" class="store-btn" id="iosBtn">
          <span class="store-icon"></span>
          <span>App Store</span>
        </a>
        <a href="#" class="store-btn" id="androidBtn">
          <span class="store-icon">▶</span>
          <span>Google Play</span>
        </a>
      </div>

      <div class="share-row">
        <button class="share-small" onclick="shareChallenge()">
          📤 把挑战发给家人 · Share with family
        </button>
      </div>
    </div>

  </div>

  <div class="footer">ScamVax · 保护家人远离语音诈骗</div>

  <audio id="hidden-audio" preload="auto">
    <source src="{fake_url}" type="audio/wav"/>
  </audio>

<script>
  var audio = document.getElementById('hidden-audio');
  var playBtn = document.getElementById('playBtn');
  var playStatus = document.getElementById('playStatus');
  var waveform = document.getElementById('waveform');
  var answerPrompt = document.getElementById('answerPrompt');
  var hasPlayed = false;
  var hasEnded = false;

  // detect language preference
  var lang = navigator.language || 'zh';
  var isCN = lang.toLowerCase().startsWith('zh');

  audio.addEventListener('play', function() {{
    playBtn.classList.add('playing');
    waveform.classList.add('active');
    playStatus.textContent = isCN ? '正在播放...' : 'Playing...';
    hasPlayed = true;
  }});

  audio.addEventListener('pause', function() {{
    if (!audio.ended) {{
      playBtn.classList.remove('playing');
      waveform.classList.remove('active');
      playStatus.textContent = isCN ? '已暂停 · 点击继续' : 'Paused · Tap to resume';
    }}
  }});

  audio.addEventListener('ended', function() {{
    hasEnded = true;
    playBtn.classList.remove('playing');
    waveform.classList.remove('active');
    playStatus.textContent = isCN ? '播放完毕 ✓' : 'Done ✓';
    // upgrade answer prompt
    answerPrompt.classList.add('ready');
    answerPrompt.textContent = isCN ? '现在作答 👇' : 'Answer now 👇';
    // after short delay, switch to guess phase
    setTimeout(function() {{
      showPhase('guess');
      setStep(2);
    }}, 800);
  }});

  function togglePlay() {{
    if (audio.paused) {{
      audio.play().catch(function(e){{ console.warn(e); }});
    }} else {{
      audio.pause();
    }}
  }}

  function makeGuess(guess) {{
    // guess is always wrong (it's always AI)
    var correct = (guess === 'ai');
    showReveal(correct);
    setStep(3);
  }}

  function showReveal(correct) {{
    showPhase('reveal');
    var header = document.getElementById('revealHeader');
    var emoji  = document.getElementById('revealEmoji');
    var verdict = document.getElementById('revealVerdict');
    var note   = document.getElementById('revealNote');

    if (correct) {{
      header.className = 'reveal-header right';
      emoji.textContent = '🎯';
      verdict.className = 'reveal-verdict right';
      verdict.textContent = isCN ? '你猜对了：这是 AI。' : 'You got it: This was AI.';
      note.innerHTML = isCN
        ? '但别得意——AI 只会越来越像真人。<br><span style="opacity:.7;">But don\'t get comfortable—AI will only sound more real.</span>'
        : 'But don\'t get comfortable—AI will only sound more real.<br><span style="opacity:.7;">但别得意——AI 只会越来越像真人。</span>';
    }} else {{
      header.className = 'reveal-header wrong';
      emoji.textContent = '😱';
      verdict.className = 'reveal-verdict wrong';
      verdict.textContent = isCN ? '你被它骗到了：这是 AI。' : 'It fooled you: This was AI.';
      note.innerHTML = isCN
        ? '现实中的骗局更有欺骗性。<br><span style="opacity:.7;">Real scam calls are even more convincing.</span>'
        : 'Real scam calls are even more convincing.<br><span style="opacity:.7;">现实中的骗局更有欺骗性。</span>';
    }}

    // set CTA link (detect platform)
    var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    var isAndroid = /android/i.test(navigator.userAgent);
    var ctaMain = document.getElementById('ctaMain');
    if (isIOS) {{
      ctaMain.href = '#';
      ctaMain.innerHTML = (isCN ? '制作我的声音克隆挑战（下载 App）' : 'Create my voice clone challenge (Get the app)') + ' <span class="cta-arrow">→</span>';
    }} else if (isAndroid) {{
      ctaMain.href = '#';
      ctaMain.innerHTML = (isCN ? '制作我的声音克隆挑战（下载 App）' : 'Create my voice clone challenge (Get the app)') + ' <span class="cta-arrow">→</span>';
    }} else {{
      ctaMain.href = '#';
    }}
  }}

  function showPhase(phase) {{
    document.getElementById('phase-listen').style.display = 'none';
    document.getElementById('phase-guess').style.display  = 'none';
    document.getElementById('phase-reveal').style.display = 'none';
    var el = document.getElementById('phase-' + phase);
    el.style.display = 'block';
    el.classList.remove('fade-in');
    void el.offsetWidth; // reflow
    el.classList.add('fade-in');
  }}

  function setStep(n) {{
    for (var i=1;i<=3;i++) {{
      var s = document.getElementById('s'+i);
      s.className = 'step' + (i<n?' done':(i===n?' active':''));
      if (i < 3) {{
        var l = document.getElementById('sl'+i);
        l.className = 'step-line' + (i<n?' done':'');
      }}
    }}
  }}

  function replayAudio() {{
    audio.currentTime = 0;
    audio.play();
  }}

  function shareChallenge() {{
    var url = window.location.href;
    var text = isCN
      ? '你能听出这是 AI 声音吗？来测一测！'
      : 'Can you tell this voice is AI? Take the challenge!';
    if (navigator.share) {{
      navigator.share({{ title: '10秒听声挑战', text: text, url: url }});
    }} else if (navigator.clipboard) {{
      navigator.clipboard.writeText(url).then(function() {{
        alert(isCN ? '链接已复制！发给家人试试吧 🎯' : 'Link copied! Share it with your family 🎯');
      }});
    }} else {{
      prompt(isCN ? '复制链接分享给家人：' : 'Copy this link:', url);
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
