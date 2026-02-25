import base64
import json
import logging
import uuid
import aiohttp
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 诈骗演习脚本（中 / 英）
SCRIPT = "现在的人工智能发展太快，只需要5秒钟的录音就能克隆一个人的声音。当骗子使用我的声音给你打电话的时候，你确定自己能分辨出来吗？即使现在能，再过半年也许就不能了。"
SCRIPT_EN = "Hey, it's me — or is it? AI can now clone my voice from just a few seconds of audio. If a scammer called you sounding exactly like this, would you know it wasn't real?"

BASE_HTTP = settings.dashscope_base_http.rstrip("/")
ENROLL_URL = f"{BASE_HTTP}/services/audio/tts/customization"
SYNTHESIS_URL = f"{BASE_HTTP}/services/aigc/multimodal-generation/generation"
TTS_MODEL = settings.tts_model
ENROLL_MODEL = settings.voice_enroll_model


class TTSVCError(Exception):
    pass


def _format_dashscope_error(resp_text: str) -> str:
    try:
        data = json.loads(resp_text)
    except Exception:
        return resp_text

    code = data.get("code") or data.get("error_code") or "UNKNOWN_CODE"
    message = data.get("message") or data.get("error_msg") or str(data)
    request_id = data.get("request_id") or data.get("requestId")
    if request_id:
        return f"{code}: {message} (request_id={request_id})"
    return f"{code}: {message}"


def _validate_tts_settings() -> None:
    if not settings.dashscope_api_key:
        raise TTSVCError("缺少 DASHSCOPE_API_KEY（或 ALIYUN_API_KEY）配置")
    if not TTS_MODEL:
        raise TTSVCError("缺少 TTS_MODEL 配置")
    if not ENROLL_MODEL:
        raise TTSVCError("缺少 VOICE_ENROLL_MODEL 配置")


async def enroll_voice(audio_bytes: bytes) -> str:
    """
    音色注册：传 base64 音频，返回 voice_name
    端点: POST /services/audio/tts/customization
    """
    audio_b64 = base64.b64encode(audio_bytes).decode()
    data_uri = f"data:audio/wav;base64,{audio_b64}"

    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    # DashScope 对 preferred_name 的格式校验较严格，按“纯字母数字 -> 不传字段”做兜底。
    name_candidates = [f"sv{uuid.uuid4().hex[:14]}", uuid.uuid4().hex[:16]]

    async def _post_create(input_payload: dict) -> tuple[int, str]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ENROLL_URL,
                headers=headers,
                json={"model": ENROLL_MODEL, "input": input_payload},
            ) as resp:
                return resp.status, await resp.text()

    logger.info("开始 voice enrollment...")
    last_error = ""
    data = None

    for preferred_name in name_candidates:
        input_payload = {
            "action": "create",
            "target_model": TTS_MODEL,
            "preferred_name": preferred_name,
            "audio": {"data": data_uri},
        }
        status, text = await _post_create(input_payload)
        if status == 200:
            data = json.loads(text)
            break
        logger.warning(
            "Voice enrollment 使用 preferred_name=%s 失败 %s: %s",
            preferred_name,
            status,
            text,
        )
        last_error = f"HTTP {status} - {_format_dashscope_error(text)}"

    # 最后再尝试一次：不传 preferred_name，让服务端自动命名（若接口支持）。
    if data is None:
        input_payload = {
            "action": "create",
            "target_model": TTS_MODEL,
            "audio": {"data": data_uri},
        }
        status, text = await _post_create(input_payload)
        if status == 200:
            data = json.loads(text)
        else:
            logger.error("Voice enrollment 失败 %s: %s", status, text)
            last_error = f"HTTP {status} - {_format_dashscope_error(text)}"
            raise TTSVCError(f"音色注册失败: {last_error}")

    voice_name = data.get("output", {}).get("voice")
    if not voice_name:
        raise TTSVCError(f"未获取到 voice name，响应: {data}")

    logger.info(f"Voice enrollment 成功，voice={voice_name}")
    return voice_name


async def delete_voice(voice_name: str) -> None:
    """
    删除已注册的音色，释放配额（账户上限 1000 条）。
    失败只记 warning，不影响主流程。
    端点: POST /services/audio/tts/customization  action="delete"
    """
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ENROLL_MODEL,
        "input": {
            "action": "delete",
            "voice": voice_name,
        },
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ENROLL_URL, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.warning(f"Voice 删除失败 {resp.status}: {text}，voice={voice_name}")
                else:
                    logger.info(f"Voice 删除成功，voice={voice_name}")
    except Exception as e:
        logger.warning(f"Voice 删除异常（已忽略）: {e}，voice={voice_name}")


async def generate_ai_audio(audio_bytes: bytes, lang: str = "zh") -> bytes:
    """
    完整流程：
    1. 音色注册 → voice_name
    2. HTTP TTS-VC 合成 → 音频 URL
    3. 下载音频，返回 WAV bytes
    4. 删除临时音色（释放账户配额）
    """
    _validate_tts_settings()
    logger.info(
        "TTS 配置: base=%s, tts_model=%s, enroll_model=%s",
        BASE_HTTP,
        TTS_MODEL,
        ENROLL_MODEL,
    )
    voice_name = await enroll_voice(audio_bytes)
    try:
        script = SCRIPT if lang == "zh" else SCRIPT_EN
        ai_audio = await _tts_via_http(voice_name, script)
        logger.info(f"AI 音频生成完成，大小={len(ai_audio)} bytes")
        return ai_audio
    finally:
        # 无论成功还是失败都删除临时音色，避免消耗账户 1000 条配额
        await delete_voice(voice_name)


async def _tts_via_http(voice_name: str, text: str) -> bytes:
    """
    HTTP TTS-VC 合成（qwen3-tts-vc-2026-01-22 非实时版本）
    POST → 取 output.audio.url → 下载音频
    """
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": TTS_MODEL,
        "input": {
            "text": text,
            "voice": voice_name,
        },
    }

    logger.info(f"开始 HTTP TTS 合成，voice={voice_name}")
    async with aiohttp.ClientSession() as session:
        async with session.post(SYNTHESIS_URL, headers=headers, json=payload) as resp:
            resp_text = await resp.text()
            if resp.status != 200:
                logger.error(f"TTS HTTP 合成失败 {resp.status}: {resp_text}")
                raise TTSVCError(f"TTS 合成失败: HTTP {resp.status} - {_format_dashscope_error(resp_text)}")
            data = json.loads(resp_text)

    audio_url = data.get("output", {}).get("audio", {}).get("url")
    if not audio_url:
        raise TTSVCError(f"响应中未找到音频 URL: {data}")

    logger.info(f"TTS 合成成功，下载音频: {audio_url[:80]}...")
    async with aiohttp.ClientSession() as session:
        async with session.get(audio_url) as resp:
            if resp.status != 200:
                raise TTSVCError(f"音频下载失败: HTTP {resp.status}")
            audio_bytes = await resp.read()

    logger.info(f"音频下载完成，大小={len(audio_bytes)} bytes")
    return audio_bytes
