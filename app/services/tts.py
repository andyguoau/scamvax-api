import base64
import json
import logging
import aiohttp
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 诈骗演习脚本（中 / 英）
SCRIPT = "现在的人工智能发展太快，只需要5秒钟的录音就能克隆一个人的声音。当骗子使用我的声音给你打电话的时候，你确定自己能分辨出来吗？即使现在能，再过半年也许就不能了。"
SCRIPT_EN = "AI voice technology has advanced so fast that just 5 seconds of audio can clone anyone's voice. If a scammer called you using my voice right now, would you be able to tell it was fake?"

ENROLL_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization"
SYNTHESIS_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
TTS_MODEL = "qwen3-tts-vc-2026-01-22"
ENROLL_MODEL = "qwen-voice-enrollment"


class TTSVCError(Exception):
    pass


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
    payload = {
        "model": ENROLL_MODEL,
        "input": {
            "action": "create",
            "target_model": TTS_MODEL,
            "preferred_name": "scamvax_voice",
            "audio": {
                "data": data_uri,
            },
        },
    }

    logger.info("开始 voice enrollment...")
    async with aiohttp.ClientSession() as session:
        async with session.post(ENROLL_URL, headers=headers, json=payload) as resp:
            text = await resp.text()
            if resp.status != 200:
                logger.error(f"Voice enrollment 失败 {resp.status}: {text}")
                raise TTSVCError(f"音色注册失败: HTTP {resp.status} - {text}")
            data = json.loads(text)

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
            "target_model": TTS_MODEL,
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
                raise TTSVCError(f"TTS 合成失败: HTTP {resp.status} - {resp_text}")
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
