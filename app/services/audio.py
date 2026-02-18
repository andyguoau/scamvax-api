import io
import logging

logger = logging.getLogger(__name__)

# 支持的音频格式（扩展名 → pydub format 名）
SUPPORTED_FORMATS = {
    "wav":  "wav",
    "mp3":  "mp3",
    "m4a":  "mp4",   # pydub 用 mp4 解析 m4a
    "aac":  "mp4",
    "ogg":  "ogg",
    "flac": "flac",
    "webm": "webm",
    "mp4":  "mp4",
    "3gp":  "3gp",
    "amr":  "amr",
}

# MIME type → 扩展名（用于从 Content-Type 推断格式）
MIME_TO_EXT = {
    "audio/wav":        "wav",
    "audio/x-wav":      "wav",
    "audio/wave":       "wav",
    "audio/mp3":        "mp3",
    "audio/mpeg":       "mp3",
    "audio/m4a":        "m4a",
    "audio/x-m4a":      "m4a",
    "audio/mp4":        "m4a",
    "audio/aac":        "aac",
    "audio/ogg":        "ogg",
    "audio/flac":       "flac",
    "audio/x-flac":     "flac",
    "audio/webm":       "webm",
    "audio/3gpp":       "3gp",
    "audio/amr":        "amr",
    "video/mp4":        "m4a",  # iOS 有时会用 video/mp4 发 m4a
    "video/webm":       "webm",
}


class AudioProcessingError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


def _detect_format(raw_bytes: bytes, filename: str = "", content_type: str = "") -> str:
    """
    推断音频格式，优先级：
    1. 文件头魔术字节（最可靠）
    2. 文件扩展名
    3. Content-Type
    4. 默认 wav
    """
    # 魔术字节检测
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WAVE":
        return "wav"
    if raw_bytes[:3] == b"ID3" or raw_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if raw_bytes[:4] in (b"fLaC",):
        return "flac"
    if raw_bytes[:4] == b"OggS":
        return "ogg"
    # M4A/MP4/AAC 检测（ftyp box）
    if len(raw_bytes) >= 8 and raw_bytes[4:8] == b"ftyp":
        return "m4a"
    if raw_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"

    # 文件扩展名
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in SUPPORTED_FORMATS:
            return ext

    # Content-Type
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in MIME_TO_EXT:
            return MIME_TO_EXT[ct]

    return "wav"  # 默认


def convert_to_wav(raw_bytes: bytes, filename: str = "", content_type: str = "") -> bytes:
    """
    将任意格式音频转换为 WAV (PCM16, 24kHz, Mono)。
    如果已经是 WAV 直接返回（节省 CPU）。
    依赖 pydub + ffmpeg（Render 环境默认带 ffmpeg）。
    """
    if len(raw_bytes) < 500:
        raise AudioProcessingError("AUDIO_TOO_SHORT", "音频文件太小，请重新录音")

    fmt = _detect_format(raw_bytes, filename, content_type)
    logger.info(f"检测到音频格式: {fmt} (filename={filename}, content_type={content_type})")

    # WAV 直接透传（已经是正确格式无需转换）
    if fmt == "wav":
        return raw_bytes

    # 使用 pydub 转换
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.warning("pydub 未安装，直接透传原始 bytes（可能导致 API 错误）")
        return raw_bytes

    try:
        pydub_fmt = SUPPORTED_FORMATS.get(fmt, fmt)
        audio = AudioSegment.from_file(io.BytesIO(raw_bytes), format=pydub_fmt)

        # 标准化：单声道、24kHz、16bit
        audio = audio.set_channels(1).set_frame_rate(24000).set_sample_width(2)

        out_buf = io.BytesIO()
        audio.export(out_buf, format="wav")
        wav_bytes = out_buf.getvalue()
        logger.info(f"格式转换成功: {fmt} → wav，原始 {len(raw_bytes)} bytes → {len(wav_bytes)} bytes")
        return wav_bytes

    except Exception as e:
        logger.error(f"音频格式转换失败 ({fmt}): {e}")
        raise AudioProcessingError("AUDIO_CONVERT_FAILED", f"无法处理音频格式 {fmt}，请上传 WAV/MP3/M4A 格式的录音")
