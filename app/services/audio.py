class AudioProcessingError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)


def validate_and_process_audio(raw_bytes: bytes) -> bytes:
    """MVP: 跳过音频校验，直接透传原始 bytes"""
    if len(raw_bytes) < 1000:
        raise AudioProcessingError("AUDIO_TOO_SHORT", "音频文件太小")
    return raw_bytes
