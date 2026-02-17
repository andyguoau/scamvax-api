import logging
import boto3
from botocore.exceptions import ClientError
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def get_audio_key(share_id: str) -> str:
    return f"challenge_{share_id}/ai.wav"


def upload_audio(share_id: str, audio_bytes: bytes) -> str:
    """上传 AI 音频到 R2，返回对象 key"""
    client = _get_client()
    key = get_audio_key(share_id)

    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=audio_bytes,
        ContentType="audio/wav",
        # 禁止公开读（R2 默认私有）
    )
    logger.info(f"已上传音频: {key}")
    return key


def download_audio(share_id: str) -> bytes:
    """从 R2 读取 AI 音频"""
    client = _get_client()
    key = get_audio_key(share_id)

    try:
        response = client.get_object(Bucket=settings.r2_bucket_name, Key=key)
        return response["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise FileNotFoundError(f"音频不存在: {key}")
        raise


def stream_audio(share_id: str):
    """流式读取 AI 音频（生成器）"""
    client = _get_client()
    key = get_audio_key(share_id)

    try:
        response = client.get_object(Bucket=settings.r2_bucket_name, Key=key)
        body = response["Body"]
        chunk_size = 65536  # 64KB
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield chunk
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise FileNotFoundError(f"音频不存在: {key}")
        raise


def delete_audio(share_id: str) -> bool:
    """从 R2 删除 AI 音频，返回是否成功"""
    client = _get_client()
    key = get_audio_key(share_id)

    try:
        client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
        logger.info(f"已删除音频: {key}")
        return True
    except ClientError as e:
        logger.error(f"删除音频失败 {key}: {e}")
        return False


def audio_exists(share_id: str) -> bool:
    """检查音频是否存在"""
    client = _get_client()
    key = get_audio_key(share_id)

    try:
        client.head_object(Bucket=settings.r2_bucket_name, Key=key)
        return True
    except ClientError:
        return False
