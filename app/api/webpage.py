import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.services import share as share_service

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["webpage"])

# ─── 挑战页面 HTML 模板 ──────────────────────────────────────────────────────

CHALLENGE_PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a; color: #f1f5f9; min-height: 100vh;
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; padding: 24px; }}
    .card {{ background: #1e293b; border-radius: 16px; padding: 32px;
             max-width: 480px; width: 100%; box-shadow: 0 25px 50px rgba(0,0,0,.5); }}
    .badge {{ background: #ef4444; color: white; font-size: 12px; font-weight: 700;
              padding: 4px 12px; border-radius: 99px; display: inline-block; margin-bottom: 16px; }}
    h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; }}
    .disclaimer {{ background: #fef3c7; color: #92400e; border-radius: 8px;
                   padding: 12px 16px; font-size: 14px; margin-bottom: 24px; }}
    .audio-block {{ background: #0f172a; border-radius: 12px; padding: 24px;
                    text-align: center; margin-bottom: 24px; }}
    audio {{ width: 100%; margin-bottom: 16px; }}
    .choices {{ display: flex; gap: 12px; margin-bottom: 16px; }}
    .choice-btn {{ flex: 1; padding: 12px; border: 2px solid #334155;
                   background: transparent; color: #f1f5f9; border-radius: 8px;
                   cursor: pointer; font-size: 15px; transition: all .2s; }}
    .choice-btn.selected {{ border-color: #6366f1; background: #312e81; }}
    .submit-btn {{ width: 100%; padding: 14px; background: #6366f1; color: white;
                   border: none; border-radius: 8px; font-size: 16px; font-weight: 600;
                   cursor: pointer; transition: background .2s; }}
    .submit-btn:disabled {{ background: #334155; cursor: not-allowed; }}
    .submit-btn:hover:not(:disabled) {{ background: #4f46e5; }}
    .result {{ display: none; }}
    .result h2 {{ font-size: 20px; margin-bottom: 12px; color: #f87171; }}
    .result p {{ color: #94a3b8; line-height: 1.6; margin-bottom: 16px; }}
    .cta-btn {{ display: block; width: 100%; padding: 14px; background: #22c55e;
                color: white; text-align: center; border-radius: 8px; font-weight: 600;
                text-decoration: none; margin-bottom: 12px; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #475569; text-align: center; }}
    .lang-switch {{ position: absolute; top: 16px; right: 16px; }}
    .lang-btn {{ background: #1e293b; color: #94a3b8; border: 1px solid #334155;
                 padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
  </style>
</head>
<body>
  <button class="lang-btn lang-switch" onclick="toggleLang()">中/EN</button>
  <div class="card">
    <span class="badge">{edu_badge}</span>
    <h1>{title}</h1>

    <div class="disclaimer">{disclaimer}</div>

    <!-- 挑战区 -->
    <div id="challenge" class="audio-block">
      <audio id="audio-player" controls>
        <source src="/api/share/{share_id}/audio" type="audio/wav"/>
      </audio>
      <div class="choices">
        <button class="choice-btn" onclick="select('real')" id="btn-real">{choice_real}</button>
        <button class="choice-btn" onclick="select('ai')" id="btn-ai">{choice_ai}</button>
      </div>
      <button class="submit-btn" id="submit-btn" disabled onclick="submit()">{submit_text}</button>
    </div>

    <!-- 结果区 -->
    <div id="result" class="result">
      <h2>{result_title}</h2>
      <p>{result_body}</p>
      <p><strong>{cta_hint}</strong></p>
      <br/>
      <a class="cta-btn" id="download-btn" href="#">{cta_text}</a>
    </div>

    <div class="footer">{footer}</div>
  </div>

  <script>
    var selected = null;
    var lang = navigator.language.startsWith('zh') ? 'zh' : 'en';

    var i18n = {{
      zh: {{
        ios_url: 'https://apps.apple.com/app/scamvax',
        android_url: 'https://play.google.com/store/apps/details?id=com.scamvax',
      }},
      en: {{
        ios_url: 'https://apps.apple.com/app/scamvax',
        android_url: 'https://play.google.com/store/apps/details?id=com.scamvax',
      }}
    }};

    function select(val) {{
      selected = val;
      document.getElementById('btn-real').classList.toggle('selected', val === 'real');
      document.getElementById('btn-ai').classList.toggle('selected', val === 'ai');
      document.getElementById('submit-btn').disabled = false;
    }}

    function submit() {{
      document.getElementById('challenge').style.display = 'none';
      document.getElementById('result').style.display = 'block';

      // 设置下载链接（UA 分流）
      var ua = navigator.userAgent;
      var dlBtn = document.getElementById('download-btn');
      var info = i18n[lang];
      if (/iPhone|iPad|iPod/.test(ua)) {{
        dlBtn.href = info.ios_url;
      }} else if (/Android/.test(ua)) {{
        dlBtn.href = info.android_url;
      }} else {{
        dlBtn.href = info.ios_url;
        dlBtn.innerHTML += ' / Android';
      }}
    }}

    function toggleLang() {{
      var newLang = lang === 'zh' ? 'en' : 'zh';
      localStorage.setItem('sv_lang', newLang);
      // 重载并带上 lang 参数
      var url = new URL(location.href);
      url.searchParams.set('lang', newLang);
      location.href = url.toString();
    }}

    // 初始化语言：URL 参数 > localStorage > 浏览器语言
    (function() {{
      var urlLang = new URLSearchParams(location.search).get('lang');
      var savedLang = localStorage.getItem('sv_lang');
      if (urlLang === 'zh' || urlLang === 'en') {{
        lang = urlLang;
        localStorage.setItem('sv_lang', lang);
      }} else if (savedLang === 'zh' || savedLang === 'en') {{
        lang = savedLang;
      }}
    }})();
  </script>
</body>
</html>"""

EXPIRED_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"/>
<title>Challenge Expired</title>
<style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;background:#0f172a;color:#f1f5f9;text-align:center;padding:24px;}}
.card{{background:#1e293b;border-radius:16px;padding:40px;max-width:400px;}}
h1{{margin-bottom:12px;color:#f87171;}}p{{color:#94a3b8;}}</style>
</head><body><div class="card">
<h1>⏰ 挑战已过期 / Challenge Expired</h1>
<p>该链接已超过 72 小时或被访问 50 次，已自动删除。<br/>
This link expired after 72h or 50 visits and was deleted.</p>
</div></body></html>"""


I18N = {
    "zh": {
        "title": "家庭防骗演习",
        "edu_badge": "📢 防骗教育",
        "disclaimer": "⚠️ 本页面包含 AI 合成语音，仅用于家庭防骗教育演习。",
        "choice_real": "✅ 真实录音",
        "choice_ai": "🤖 AI 生成",
        "submit_text": "提交判断",
        "result_title": "🎯 这是 AI 合成语音！",
        "result_body": "仅凭听觉，你无法可靠地验证对方身份。AI 可以完美模拟你亲人的声音。",
        "cta_hint": "💡 立即建立家庭安全暗号：任何要求转账或验证码的电话，必须用暗号验证。",
        "cta_text": "制作我的挑战，提醒亲友防骗 →",
        "footer": "该挑战将在 72 小时或 50 次访问后自动删除",
    },
    "en": {
        "title": "Family Anti-Scam Exercise",
        "edu_badge": "📢 Scam Awareness",
        "disclaimer": "⚠️ This page contains AI-synthesized voice, for family anti-scam education only.",
        "choice_real": "✅ Real Voice",
        "choice_ai": "🤖 AI Generated",
        "submit_text": "Submit Answer",
        "result_title": "🎯 This was AI-generated!",
        "result_body": "You cannot reliably verify someone's identity by voice alone. AI can perfectly clone your family member's voice.",
        "cta_hint": "💡 Set a family safe word now: any call requesting money or codes must be verified with the safe word.",
        "cta_text": "Create My Challenge & Protect My Family →",
        "footer": "This challenge will be auto-deleted after 72 hours or 50 visits",
    },
}


# ─── Route ────────────────────────────────────────────────────────────────────

@router.get("/s/{share_id}", response_class=HTMLResponse)
async def challenge_page(
    share_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    lang: str | None = None,
):
    """
    挑战网页主入口：
    - 原子性计数 + 过期检查
    - 过期 → 删除 + 返回过期页
    - 正常 → 返回挑战 HTML
    语言优先级：URL ?lang= > Accept-Language header
    """
    share = await share_service.access_share(db, share_id)

    if share is None:
        return HTMLResponse(content=EXPIRED_PAGE, status_code=410)

    # 语言检测：URL 参数 > Accept-Language
    if lang not in ("zh", "en"):
        accept_lang = request.headers.get("accept-language", "")
        lang = "zh" if "zh" in accept_lang else "en"

    t = I18N[lang]

    html = CHALLENGE_PAGE.format(
        lang=lang,
        share_id=share_id,
        **t,
    )
    return HTMLResponse(content=html)
