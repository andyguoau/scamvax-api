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

PRIVACY_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Privacy Policy — ScamVax</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f172a; color: #f1f5f9; min-height: 100vh;
      padding: 32px 24px 64px;
    }}
    .container {{ max-width: 720px; margin: 0 auto; }}
    .lang-bar {{
      display: flex; justify-content: flex-end; margin-bottom: 24px; gap: 8px;
    }}
    .lang-btn {{
      background: #1e293b; color: #94a3b8; border: 1px solid #334155;
      padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;
      transition: all .2s;
    }}
    .lang-btn.active {{ background: #6366f1; color: white; border-color: #6366f1; }}
    .badge {{
      background: #6366f1; color: white; font-size: 11px; font-weight: 700;
      padding: 3px 10px; border-radius: 99px; display: inline-block; margin-bottom: 12px;
      letter-spacing: .04em; text-transform: uppercase;
    }}
    h1 {{ font-size: 28px; font-weight: 800; margin-bottom: 6px; line-height: 1.2; }}
    .meta {{ color: #64748b; font-size: 13px; margin-bottom: 40px; }}
    h2 {{
      font-size: 17px; font-weight: 700; color: #c7d2fe;
      margin: 36px 0 14px; padding-left: 14px;
      border-left: 3px solid #6366f1;
    }}
    p {{ color: #cbd5e1; line-height: 1.75; margin-bottom: 12px; font-size: 15px; }}
    ul {{ padding-left: 20px; margin-bottom: 12px; }}
    li {{ color: #cbd5e1; line-height: 1.7; margin-bottom: 6px; font-size: 15px; }}
    li strong {{ color: #f1f5f9; }}
    .table-wrap {{ overflow-x: auto; margin-bottom: 16px; }}
    table {{
      width: 100%; border-collapse: collapse; font-size: 14px;
    }}
    th {{
      background: #1e293b; color: #94a3b8; text-align: left;
      padding: 10px 14px; font-weight: 600; border-bottom: 1px solid #334155;
    }}
    td {{
      padding: 10px 14px; border-bottom: 1px solid #1e293b; color: #cbd5e1;
      vertical-align: top;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .highlight {{
      background: #1e293b; border-radius: 10px; padding: 16px 20px;
      margin-bottom: 16px; border: 1px solid #334155;
    }}
    .highlight p {{ margin: 0; }}
    .pill {{
      display: inline-block; background: #0f172a; border: 1px solid #334155;
      color: #94a3b8; font-size: 12px; padding: 2px 10px; border-radius: 99px;
      margin: 2px 4px 2px 0;
    }}
    a {{ color: #818cf8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .footer {{
      margin-top: 48px; padding-top: 24px; border-top: 1px solid #1e293b;
      text-align: center; font-size: 13px; color: #475569;
    }}
    /* language panels */
    .panel-en, .panel-zh {{ display: none; }}
    .panel-en.active, .panel-zh.active {{ display: block; }}
  </style>
</head>
<body>
<div class="container">
  <div class="lang-bar">
    <button class="lang-btn active" id="btn-en" onclick="switchLang('en')">English</button>
    <button class="lang-btn" id="btn-zh" onclick="switchLang('zh')">中文</button>
  </div>

  <!-- ═══════════════════════════ ENGLISH ═══════════════════════════ -->
  <div class="panel-en active" id="panel-en">
    <span class="badge">Privacy Policy</span>
    <h1>ScamVax Privacy Policy</h1>
    <p class="meta">Effective date: 22 February 2026 &nbsp;·&nbsp; Last updated: 22 February 2026</p>

    <p>ScamVax ("we", "our", or "the App") is an anti-scam education tool. This policy explains what data we collect, why, how it is used, and your rights. We keep data collection to the minimum required for the App to function.</p>

    <h2>1. What Data We Collect</h2>
    <div class="table-wrap">
      <table>
        <tr>
          <th>Category</th>
          <th>What exactly</th>
          <th>Source</th>
        </tr>
        <tr>
          <td><strong>Audio Data</strong></td>
          <td>A voice recording you choose to submit for generating an AI-cloned voice challenge. The original recording is <em>never stored</em>; it is processed in memory and discarded immediately after synthesis.</td>
          <td>Provided by you in-app</td>
        </tr>
        <tr>
          <td><strong>Device Identifier</strong></td>
          <td>A random identifier generated and stored on your device (not the system advertising ID / IDFA). Used solely for rate-limiting: preventing abuse by limiting how many challenges one device may create.</td>
          <td>Generated by the App on first launch</td>
        </tr>
        <tr>
          <td><strong>Advertising Data</strong></td>
          <td>We declare this category in App Store Connect because the App's privacy label covers potential future use. Currently, we do <strong>not</strong> use any advertising SDK, display ads, or share data with advertising networks. If this changes, we will update this policy before doing so.</td>
          <td>—</td>
        </tr>
      </table>
    </div>

    <p>We do <strong>not</strong> collect names, email addresses, phone numbers, location, contacts, browsing history, or health data.</p>

    <h2>2. Why We Collect It (Purpose)</h2>
    <ul>
      <li><strong>Audio Data</strong> — to generate an AI voice-clone of your recording so you can share a realistic "could you tell?" challenge with family members. The original recording is discarded the moment synthesis completes.</li>
      <li><strong>Device Identifier</strong> — to enforce a per-device creation limit and prevent service abuse (rate limiting / anti-fraud). It is not used for analytics, profiling, or advertising.</li>
    </ul>

    <h2>3. Tracking &amp; Cross-App Data Use</h2>
    <div class="highlight">
      <p>We do <strong>not</strong> track you across third-party apps or websites. The device identifier we use is not the system advertising ID (IDFA) and is not shared with any advertising or analytics network. No data is used for targeted advertising.</p>
    </div>

    <h2>4. Third-Party Processors</h2>
    <p>We use the following service providers who may process your data on our behalf:</p>
    <div class="table-wrap">
      <table>
        <tr>
          <th>Provider</th>
          <th>Role</th>
          <th>Data involved</th>
          <th>Privacy info</th>
        </tr>
        <tr>
          <td><strong>Alibaba Cloud (DashScope)</strong></td>
          <td>Voice synthesis API — your audio is sent for cloning and the synthesised audio is returned. Alibaba Cloud processes your audio under API terms.</td>
          <td>Audio (in transit, for synthesis only)</td>
          <td><a href="https://www.alibabacloud.com/en/privacy-policy" target="_blank" rel="noopener">Privacy Policy</a></td>
        </tr>
        <tr>
          <td><strong>Cloudflare (R2)</strong></td>
          <td>Object storage — the AI-generated audio file is stored here and served via CDN to challenge link visitors.</td>
          <td>AI-generated audio only</td>
          <td><a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener">Privacy Policy</a></td>
        </tr>
        <tr>
          <td><strong>Render</strong></td>
          <td>Backend hosting — the API server runs on Render's infrastructure.</td>
          <td>API request data (audio, device ID)</td>
          <td><a href="https://render.com/privacy" target="_blank" rel="noopener">Privacy Policy</a></td>
        </tr>
      </table>
    </div>
    <p>We do not sell your data. We do not share data with any party for advertising purposes.</p>

    <h2>5. Data Retention &amp; Deletion</h2>
    <ul>
      <li><strong>Original recording</strong> — discarded in memory immediately after synthesis. Never written to disk or storage.</li>
      <li><strong>AI-generated audio</strong> — stored in Cloudflare R2 and automatically deleted after <strong>72 hours</strong> or <strong>50 visits</strong> to the challenge link, whichever occurs first. Our server runs a cleanup job every 30 minutes.</li>
      <li><strong>Device identifier</strong> — stored in our database linked to challenge records; deleted when its associated challenge expires (see above).</li>
      <li><strong>Server logs</strong> — retained for up to 30 days for operational purposes, then purged.</li>
    </ul>

    <h2>6. Your Rights &amp; Deletion Requests</h2>
    <p>Because we do not require account creation, we hold no user profile or account data. If you wish to request early deletion of a specific challenge (AI audio) you created, or have any privacy concern, please contact us:</p>
    <div class="highlight">
      <p>📧 <a href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a></p>
    </div>
    <p>Include a description of your request and, if possible, the challenge URL. We will respond within 30 days.</p>
    <p>Depending on your jurisdiction you may have rights to access, correct, or delete your personal data (e.g. under GDPR, CCPA, or Australian Privacy Act). We will honour reasonable requests.</p>

    <h2>7. Security</h2>
    <ul>
      <li>All data is transmitted over <strong>HTTPS / TLS</strong>.</li>
      <li>Cloudflare R2 storage uses server-side encryption at rest.</li>
      <li>Access to our backend and storage is restricted to authorised personnel via least-privilege credentials.</li>
      <li>Your original recording is processed in memory only and is never written to persistent storage.</li>
    </ul>

    <h2>8. Children's Privacy</h2>
    <p>ScamVax is not directed at children under 13 (or 16 in the EU). We do not knowingly collect personal data from children. If you believe we have inadvertently done so, please contact us and we will delete it promptly.</p>

    <h2>9. Changes to This Policy</h2>
    <p>We may update this policy from time to time. We will update the "Last updated" date above. Continued use of the App after changes constitutes acceptance of the revised policy.</p>

    <h2>10. Contact</h2>
    <p>For privacy-related questions or requests:</p>
    <div class="highlight">
      <p>📧 <a href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a><br/>
      <span style="color:#64748b;font-size:13px;">ScamVax — anti-scam education platform</span></p>
    </div>
  </div>

  <!-- ═══════════════════════════ 中文 ═══════════════════════════ -->
  <div class="panel-zh" id="panel-zh">
    <span class="badge">隐私政策</span>
    <h1>ScamVax 隐私政策</h1>
    <p class="meta">生效日期：2026年2月22日 &nbsp;·&nbsp; 最后更新：2026年2月22日</p>

    <p>ScamVax（以下简称"我们"或"本应用"）是一款防骗教育工具。本政策说明我们收集哪些数据、为何收集、如何使用，以及您的权利。我们将数据收集限制在应用正常运行所必需的最低范围。</p>

    <h2>1. 我们收集哪些数据</h2>
    <div class="table-wrap">
      <table>
        <tr>
          <th>类别</th>
          <th>具体内容</th>
          <th>来源</th>
        </tr>
        <tr>
          <td><strong>音频数据</strong></td>
          <td>您在应用内主动提交的语音录音，用于生成 AI 声音克隆挑战。<em>原始录音从不存储</em>——合成完成后立即在内存中丢弃。</td>
          <td>您在应用内提供</td>
        </tr>
        <tr>
          <td><strong>设备标识符</strong></td>
          <td>由应用在首次启动时随机生成并本地保存的 ID（非系统广告标识符 IDFA）。仅用于频率限制：防止单一设备在短时间内创建过多挑战。</td>
          <td>应用首次启动时生成</td>
        </tr>
        <tr>
          <td><strong>广告数据</strong></td>
          <td>我们在 App Store Connect 隐私标签中声明了该类别，以覆盖潜在的未来场景。<strong>目前</strong>，我们不集成任何广告 SDK、不投放广告、不与广告网络共享数据。如有变更，我们将在实施前更新本政策。</td>
          <td>—</td>
        </tr>
      </table>
    </div>
    <p>我们<strong>不</strong>收集姓名、邮箱、手机号、位置、通讯录、浏览记录或健康数据。</p>

    <h2>2. 收集目的</h2>
    <ul>
      <li><strong>音频数据</strong> — 生成您声音的 AI 克隆版本，以便您将"你能分辨吗？"挑战分享给家人。原始录音在合成完成后立即丢弃。</li>
      <li><strong>设备标识符</strong> — 执行每台设备的创建频率限制，防止服务滥用（频控 / 反作弊）。不用于数据分析、用户画像或广告。</li>
    </ul>

    <h2>3. 跨应用追踪（Tracking）</h2>
    <div class="highlight">
      <p>我们<strong>不</strong>通过跨第三方应用或网站的方式追踪您。我们使用的设备标识符并非系统广告 ID（IDFA），也不会与任何广告或统计网络共享。没有任何数据用于定向广告。</p>
    </div>

    <h2>4. 第三方数据处理方</h2>
    <p>我们使用以下服务商代我们处理数据：</p>
    <div class="table-wrap">
      <table>
        <tr>
          <th>服务商</th>
          <th>角色</th>
          <th>涉及数据</th>
          <th>隐私信息</th>
        </tr>
        <tr>
          <td><strong>阿里云（DashScope）</strong></td>
          <td>语音合成 API — 您的音频在 API 调用期间发送至阿里云进行声音克隆，合成后返回结果。</td>
          <td>音频（传输中，仅用于合成）</td>
          <td><a href="https://www.alibabacloud.com/en/privacy-policy" target="_blank" rel="noopener">隐私政策</a></td>
        </tr>
        <tr>
          <td><strong>Cloudflare（R2）</strong></td>
          <td>对象存储 — AI 生成的音频存储于此，通过 CDN 分发给访问挑战链接的用户。</td>
          <td>仅 AI 生成音频</td>
          <td><a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener">隐私政策</a></td>
        </tr>
        <tr>
          <td><strong>Render</strong></td>
          <td>后端托管 — API 服务器运行于 Render 基础设施上。</td>
          <td>API 请求数据（音频、设备 ID）</td>
          <td><a href="https://render.com/privacy" target="_blank" rel="noopener">隐私政策</a></td>
        </tr>
      </table>
    </div>
    <p>我们不出售您的数据，也不以任何形式将数据共享给广告方。</p>

    <h2>5. 数据保留与删除</h2>
    <ul>
      <li><strong>原始录音</strong> — 在内存中处理，合成完成后立即丢弃，从不写入磁盘或持久化存储。</li>
      <li><strong>AI 生成音频</strong> — 存储于 Cloudflare R2，在挑战链接被访问 <strong>50 次</strong>或距创建 <strong>72 小时</strong>（以先达到者为准）后自动删除。服务器每 30 分钟执行一次清理任务。</li>
      <li><strong>设备标识符</strong> — 存储于我们的数据库，与挑战记录绑定；挑战到期（见上文）时一并删除。</li>
      <li><strong>服务器日志</strong> — 出于运营需要保留最多 30 天，随后清除。</li>
    </ul>

    <h2>6. 您的权利与删除请求</h2>
    <p>由于本应用无需注册账号，我们不持有用户档案或账号信息。如需提前删除您创建的某个挑战（AI 音频），或有其他隐私问题，请联系我们：</p>
    <div class="highlight">
      <p>📧 <a href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a></p>
    </div>
    <p>请在邮件中描述您的请求，如方便请附上挑战链接。我们将在 30 天内回复。</p>
    <p>根据您所在地区适用的法律（例如 GDPR、CCPA、澳大利亚《隐私法》），您可能享有访问、更正或删除个人数据的权利。我们将合理响应此类请求。</p>

    <h2>7. 安全措施</h2>
    <ul>
      <li>所有数据传输均通过 <strong>HTTPS / TLS</strong> 加密。</li>
      <li>Cloudflare R2 存储使用服务端静态加密。</li>
      <li>后端和存储的访问权限受最小权限原则控制，仅授权人员可访问。</li>
      <li>原始录音仅在内存中处理，不写入任何持久化存储。</li>
    </ul>

    <h2>8. 儿童隐私</h2>
    <p>ScamVax 不面向 13 岁以下（欧盟地区为 16 岁以下）的儿童。我们不会有意收集儿童的个人数据。如您认为我们无意中收集了儿童数据，请联系我们，我们将立即删除。</p>

    <h2>9. 政策变更</h2>
    <p>我们可能不时更新本政策，届时将同步更新上方的"最后更新"日期。在变更后继续使用本应用，即视为接受修订后的政策。</p>

    <h2>10. 联系方式</h2>
    <p>如有任何隐私相关问题或请求：</p>
    <div class="highlight">
      <p>📧 <a href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a><br/>
      <span style="color:#64748b;font-size:13px;">ScamVax — 家庭防骗教育平台</span></p>
    </div>
  </div>

  <div class="footer">
    © 2026 ScamVax &nbsp;·&nbsp; <a href="/privacy">Privacy Policy</a>
  </div>
</div>

<script>
  function switchLang(lang) {{
    document.getElementById('panel-en').classList.toggle('active', lang === 'en');
    document.getElementById('panel-zh').classList.toggle('active', lang === 'zh');
    document.getElementById('btn-en').classList.toggle('active', lang === 'en');
    document.getElementById('btn-zh').classList.toggle('active', lang === 'zh');
    localStorage.setItem('sv_privacy_lang', lang);
  }}
  // auto-detect
  (function() {{
    var saved = localStorage.getItem('sv_privacy_lang');
    var browserLang = (navigator.language || '').toLowerCase();
    if (saved === 'zh' || saved === 'en') {{
      switchLang(saved);
    }} else if (browserLang.startsWith('zh')) {{
      switchLang('zh');
    }}
  }})();
</script>
</body>
</html>"""


SUPPORT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Support — ScamVax</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f172a; color: #f1f5f9; min-height: 100vh;
      padding: 32px 24px 64px;
    }}
    .container {{ max-width: 680px; margin: 0 auto; }}
    .lang-bar {{
      display: flex; justify-content: flex-end; margin-bottom: 24px; gap: 8px;
    }}
    .lang-btn {{
      background: #1e293b; color: #94a3b8; border: 1px solid #334155;
      padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px;
      transition: all .2s;
    }}
    .lang-btn.active {{ background: #6366f1; color: white; border-color: #6366f1; }}
    .badge {{
      background: #22c55e; color: white; font-size: 11px; font-weight: 700;
      padding: 3px 10px; border-radius: 99px; display: inline-block; margin-bottom: 12px;
      letter-spacing: .04em; text-transform: uppercase;
    }}
    h1 {{ font-size: 28px; font-weight: 800; margin-bottom: 6px; line-height: 1.2; }}
    .meta {{ color: #64748b; font-size: 13px; margin-bottom: 32px; }}
    h2 {{
      font-size: 16px; font-weight: 700; color: #c7d2fe;
      margin: 32px 0 12px; padding-left: 14px;
      border-left: 3px solid #6366f1;
    }}
    p {{ color: #cbd5e1; line-height: 1.75; margin-bottom: 10px; font-size: 15px; }}
    .contact-card {{
      background: #1e293b; border-radius: 12px; padding: 24px 28px;
      border: 1px solid #334155; margin-bottom: 16px;
      display: flex; align-items: flex-start; gap: 16px;
    }}
    .contact-icon {{ font-size: 28px; line-height: 1; flex-shrink: 0; margin-top: 2px; }}
    .contact-title {{ font-size: 15px; font-weight: 700; color: #f1f5f9; margin-bottom: 4px; }}
    .contact-desc {{ font-size: 13px; color: #64748b; margin-bottom: 10px; line-height: 1.5; }}
    .contact-link {{
      display: inline-block; background: #6366f1; color: white;
      padding: 8px 18px; border-radius: 8px; font-size: 14px; font-weight: 600;
      text-decoration: none; transition: background .2s;
    }}
    .contact-link:hover {{ background: #4f46e5; }}
    .faq-item {{
      background: #1e293b; border-radius: 10px; padding: 18px 20px;
      margin-bottom: 10px; border: 1px solid #1e293b;
    }}
    .faq-q {{ font-size: 14px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px; }}
    .faq-a {{ font-size: 14px; color: #94a3b8; line-height: 1.65; }}
    a {{ color: #818cf8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .footer {{
      margin-top: 48px; padding-top: 24px; border-top: 1px solid #1e293b;
      text-align: center; font-size: 13px; color: #475569;
    }}
    .panel-en, .panel-zh {{ display: none; }}
    .panel-en.active, .panel-zh.active {{ display: block; }}
  </style>
</head>
<body>
<div class="container">
  <div class="lang-bar">
    <button class="lang-btn active" id="btn-en" onclick="switchLang('en')">English</button>
    <button class="lang-btn" id="btn-zh" onclick="switchLang('zh')">中文</button>
  </div>

  <!-- ═══════════════════════════ ENGLISH ═══════════════════════════ -->
  <div class="panel-en active" id="panel-en">
    <span class="badge">Support</span>
    <h1>ScamVax Support</h1>
    <p class="meta">We're here to help. Get in touch or browse the FAQ below.</p>

    <h2>Contact Us</h2>
    <div class="contact-card">
      <div class="contact-icon">📧</div>
      <div>
        <div class="contact-title">Email Support</div>
        <div class="contact-desc">For any issue, bug report, feedback, or privacy request. We aim to respond within 2 business days.</div>
        <a class="contact-link" href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a>
      </div>
    </div>

    <h2>Frequently Asked Questions</h2>

    <div class="faq-item">
      <div class="faq-q">Is my voice recording stored permanently?</div>
      <div class="faq-a">No. Your original recording is processed in memory and discarded immediately after the AI voice is generated. It is never written to disk or long-term storage.</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">How long does the challenge link stay active?</div>
      <div class="faq-a">The shared challenge link (and the AI-generated audio) is automatically deleted after <strong style="color:#f1f5f9">72 hours</strong> or <strong style="color:#f1f5f9">50 visits</strong>, whichever comes first.</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">Can I delete my challenge early?</div>
      <div class="faq-a">Yes. Email us at <a href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a> with the challenge URL and we will delete it promptly.</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">Why does the app ask for microphone access?</div>
      <div class="faq-a">ScamVax needs your microphone to record a short voice sample. This recording is used solely to generate the AI voice clone for your challenge — it is never stored or shared.</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">The AI voice generation failed. What should I do?</div>
      <div class="faq-a">Please check your internet connection and try again. If the problem persists, email us and include any error message you see — we'll investigate.</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">Is the app free?</div>
      <div class="faq-a">ScamVax requires a one-time unlock to create challenges. If you have questions about access or purchasing, please contact us.</div>
    </div>
  </div>

  <!-- ═══════════════════════════ 中文 ═══════════════════════════ -->
  <div class="panel-zh" id="panel-zh">
    <span class="badge">支持</span>
    <h1>ScamVax 客户支持</h1>
    <p class="meta">遇到问题？联系我们或查看下方常见问题。</p>

    <h2>联系我们</h2>
    <div class="contact-card">
      <div class="contact-icon">📧</div>
      <div>
        <div class="contact-title">邮件支持</div>
        <div class="contact-desc">如有任何问题、Bug 反馈、功能建议或隐私请求，请发送邮件。我们通常在 2 个工作日内回复。</div>
        <a class="contact-link" href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a>
      </div>
    </div>

    <h2>常见问题</h2>

    <div class="faq-item">
      <div class="faq-q">我的录音会被永久保存吗？</div>
      <div class="faq-a">不会。您的原始录音仅在内存中处理，AI 语音生成完成后立即丢弃，从不写入磁盘或持久化存储。</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">挑战链接会保留多久？</div>
      <div class="faq-a">共享的挑战链接（及其 AI 生成音频）将在 <strong style="color:#f1f5f9">72 小时</strong>后或被访问 <strong style="color:#f1f5f9">50 次</strong>后自动删除，以先到者为准。</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">我可以提前删除我的挑战吗？</div>
      <div class="faq-a">可以。请将挑战链接发送至 <a href="mailto:junqiangguo177@gmail.com">junqiangguo177@gmail.com</a>，我们会尽快处理。</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">为什么应用需要麦克风权限？</div>
      <div class="faq-a">ScamVax 需要麦克风录制一段简短的语音样本，仅用于生成 AI 声音克隆挑战。录音不会被存储或分享。</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">AI 语音生成失败了，怎么办？</div>
      <div class="faq-a">请检查网络连接后重试。如果问题持续，请将应用内显示的错误信息发送至我们的邮箱，我们会协助排查。</div>
    </div>

    <div class="faq-item">
      <div class="faq-q">应用是免费的吗？</div>
      <div class="faq-a">ScamVax 需要一次性解锁才能创建挑战。如有关于访问权限或购买的问题，请联系我们。</div>
    </div>
  </div>

  <div class="footer">
    © 2026 ScamVax &nbsp;·&nbsp;
    <a href="/support">Support</a> &nbsp;·&nbsp;
    <a href="/privacy">Privacy Policy</a>
  </div>
</div>

<script>
  function switchLang(lang) {{
    document.getElementById('panel-en').classList.toggle('active', lang === 'en');
    document.getElementById('panel-zh').classList.toggle('active', lang === 'zh');
    document.getElementById('btn-en').classList.toggle('active', lang === 'en');
    document.getElementById('btn-zh').classList.toggle('active', lang === 'zh');
    localStorage.setItem('sv_support_lang', lang);
  }}
  (function() {{
    var saved = localStorage.getItem('sv_support_lang');
    var browserLang = (navigator.language || '').toLowerCase();
    if (saved === 'zh' || saved === 'en') {{
      switchLang(saved);
    }} else if (browserLang.startsWith('zh')) {{
      switchLang('zh');
    }}
  }})();
</script>
</body>
</html>"""


@router.get("/support", response_class=HTMLResponse)
async def support_page():
    """支持页面（中英双语）"""
    return HTMLResponse(content=SUPPORT_PAGE.format())


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    """隐私政策页面（中英双语）"""
    # PRIVACY_PAGE uses {{ }} escaping (same style as other templates);
    # .format() with no args resolves them to literal { } for valid HTML/CSS/JS
    return HTMLResponse(content=PRIVACY_PAGE.format())


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
