import io
import logging
import numpy as np
import soundfile as sf
import librosa
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

TARGET_SR = 24000
TARGET_CHANNELS = 1
TARGET_SUBTYPE = "PCM_16"


class AudioProcessingError(Exception):
    """音频处理错误基类"""
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


def validate_and_process_audio(raw_bytes: bytes) -> bytes:
    """
    校验并处理上传音频：
    1. 解析格式
    2. 校验时长（<10s 拒绝，>20s 截断）
    3. 重采样至 24kHz mono PCM16
    4. 返回处理后的 WAV bytes
    """
    try:
        buf = io.BytesIO(raw_bytes)
        data, sr = sf.read(buf, always_2d=False)
    except Exception as e:
        logger.warning(f"音频解析失败: {e}")
        raise AudioProcessingError("AUDIO_PARSE_FAILED", f"无法解析音频文件: {e}")

    # 转 mono
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    duration = len(data) / sr

    # 时长检查
    if duration < settings.audio_min_duration_s:
        raise AudioProcessingError(
            "AUDIO_TOO_SHORT",
            f"录音时长 {duration:.1f}s，最少需要 {settings.audio_min_duration_s}s"
        )

    # 截断超长音频
    if duration > settings.audio_max_duration_s:
        max_samples = int(settings.audio_max_duration_s * sr)
        data = data[:max_samples]
        logger.info(f"音频已截断至 {settings.audio_max_duration_s}s")

    # 重采样
    if sr != TARGET_SR:
        data = librosa.resample(data, orig_sr=sr, target_sr=TARGET_SR)
        logger.info(f"已从 {sr}Hz 重采样至 {TARGET_SR}Hz")

    # 归一化到 [-1, 1]
    max_val = np.max(np.abs(data))
    if max_val > 0:
        data = data / max_val * 0.95

    # 转回 int16 WAV bytes
    out_buf = io.BytesIO()
    sf.write(out_buf, data, TARGET_SR, subtype=TARGET_SUBTYPE, format="WAV")
    return out_buf.getvalue()


def get_audio_duration(raw_bytes: bytes) -> float:
    """仅返回时长，不处理"""
    buf = io.BytesIO(raw_bytes)
    info = sf.info(buf)
    return info.duration
