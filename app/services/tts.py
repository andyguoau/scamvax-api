import asyncio
import base64
import json
import logging
import uuid
import aiohttp
import websockets
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 预设诈骗演习脚本（中英双语）
SCRIPTS = {
    "zh": "妈，是我，我现在遇到点麻烦，需要你马上转一笔钱给我，不要告诉别人，你能帮我吗？",
    "en": "Mom, it's me. I'm in trouble right now and I need you to transfer some money immediately. Please don't tell anyone. Can you help me?",
}


class TTSVCError(Exception):
    """语音克隆服务错误"""
    pass


async def enroll_voice(audio_bytes: bytes) -> str:
    """
    第一步：上传用户录音，获取 voice_id（音色注册）
    使用 DashScope voice enrollment API
    """
    audio_b64 = base64.b64encode(audio_bytes).decode()

    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.voice_enroll_model,
        "input": {
            "audio": audio_b64,
            "format": "wav",
        },
    }

    url = f"{settings.dashscope_base_http}/services/audio/tts/voice-enrollment"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Voice enrollment 失败 {resp.status}: {text}")
                raise TTSVCError(f"音色注册失败: HTTP {resp.status}")
            data = await resp.json()

    voice_id = data.get("output", {}).get("voice_id")
    if not voice_id:
        raise TTSVCError(f"未获取到 voice_id，响应: {data}")

    logger.info(f"Voice enrollment 成功，voice_id={voice_id}")
    return voice_id


async def generate_ai_audio(audio_bytes: bytes, lang: str = "zh") -> bytes:
    """
    完整流程：
    1. 音色注册 → voice_id
    2. WebSocket 实时 TTS-VC 生成 AI 音频
    3. 返回合成 WAV bytes
    """
    script = SCRIPTS.get(lang, SCRIPTS["zh"])

    # Step 1: 注册音色
    voice_id = await enroll_voice(audio_bytes)

    # Step 2: WebSocket TTS-VC
    ai_audio = await _tts_vc_via_websocket(voice_id, script)

    logger.info(f"AI 音频生成完成，大小={len(ai_audio)} bytes")
    return ai_audio


async def _tts_vc_via_websocket(voice_id: str, script: str) -> bytes:
    """
    通过 WebSocket 调用 Qwen3-TTS-VC 生成音频
    协议参考 DashScope Realtime API
    """
    task_id = uuid.uuid4().hex
    headers = {"Authorization": f"Bearer {settings.dashscope_api_key}"}
    uri = f"{settings.dashscope_base_ws}/inference"

    audio_chunks = []

    async with websockets.connect(uri, additional_headers=headers) as ws:
        # 发送 run-task 指令
        run_task_msg = {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "tts",
                "function": "SpeechSynthesizer",
                "model": settings.tts_model,
                "parameters": {
                    "text_type": "PlainText",
                    "voice": voice_id,
                    "format": "wav",
                    "sample_rate": 24000,
                },
                "input": {},
            },
        }
        await ws.send(json.dumps(run_task_msg))

        # 等待 task-started 确认
        ack = json.loads(await ws.recv())
        if ack.get("header", {}).get("event") != "task-started":
            raise TTSVCError(f"Task 未正常启动: {ack}")

        # 发送文本
        continue_msg = {
            "header": {
                "action": "continue-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "input": {"text": script},
            },
        }
        await ws.send(json.dumps(continue_msg))

        # 发送结束信号
        finish_msg = {
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {"input": {}},
        }
        await ws.send(json.dumps(finish_msg))

        # 接收音频流
        async for message in ws:
            if isinstance(message, bytes):
                # 二进制帧 = 音频数据
                audio_chunks.append(message)
            else:
                event_data = json.loads(message)
                event = event_data.get("header", {}).get("event", "")
                if event == "task-finished":
                    logger.info("TTS-VC 任务完成")
                    break
                elif event == "task-failed":
                    error = event_data.get("payload", {}).get("message", "未知错误")
                    raise TTSVCError(f"TTS-VC 生成失败: {error}")

    if not audio_chunks:
        raise TTSVCError("未收到任何音频数据")

    return b"".join(audio_chunks)
