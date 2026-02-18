import base64
import json
import logging
import aiohttp
import websockets
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 固定诈骗演习脚本
SCRIPT = "妈，是我，我现在遇到点麻烦，需要你马上转一笔钱给我，不要告诉别人，你能帮我吗？"

ENROLL_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization"
WS_URL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?model=qwen3-tts-vc-realtime-2026-01-15"
TTS_MODEL = "qwen3-tts-vc-realtime-2026-01-15"
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


async def generate_ai_audio(audio_bytes: bytes, lang: str = "zh") -> bytes:
    """
    完整流程：
    1. 音色注册 → voice_name
    2. WebSocket TTS-VC 合成
    3. 返回 PCM/WAV bytes
    """
    voice_name = await enroll_voice(audio_bytes)
    ai_audio = await _tts_via_websocket(voice_name, SCRIPT)
    logger.info(f"AI 音频生成完成，大小={len(ai_audio)} bytes")
    return ai_audio


async def _tts_via_websocket(voice_name: str, text: str) -> bytes:
    """
    WebSocket TTS-VC 合成
    协议: session.update → input_text_buffer.append → response.audio.delta
    """
    headers = {"Authorization": f"Bearer {settings.dashscope_api_key}"}
    audio_chunks = []

    async with websockets.connect(WS_URL, extra_headers=headers) as ws:
        # 1. 配置 session
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "voice": voice_name,
                "mode": "server_commit",
                "response_format": "pcm",
                "sample_rate": 24000,
            },
        }))

        # 等待 session.updated 确认
        ack = json.loads(await ws.recv())
        logger.info(f"Session ack: {ack.get('type')}")
        if ack.get("type") == "error":
            raise TTSVCError(f"Session 配置失败: {ack}")

        # 2. 发送文本
        await ws.send(json.dumps({
            "type": "input_text_buffer.append",
            "text": text,
        }))

        # 3. 提交生成（server_commit 模式下自动开始生成，不需要 response.create）
        await ws.send(json.dumps({
            "type": "input_text_buffer.commit",
        }))

        # 4. 接收音频流
        async for message in ws:
            if isinstance(message, bytes):
                audio_chunks.append(message)
                continue

            event = json.loads(message)
            event_type = event.get("type", "")
            logger.info(f"WS event: {event_type}")

            if event_type == "response.audio.delta":
                # base64 编码的 PCM 片段
                delta = event.get("delta", "")
                if delta:
                    audio_chunks.append(base64.b64decode(delta))

            elif event_type == "response.done":
                logger.info("TTS 生成完成")
                break

            elif event_type == "error":
                raise TTSVCError(f"TTS 生成失败: {event}")

    if not audio_chunks:
        raise TTSVCError("未收到任何音频数据")

    return b"".join(audio_chunks)
