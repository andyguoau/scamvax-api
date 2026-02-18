import logging
import boto3
from botocore.exceptions import ClientError
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.get_r2_endpoint(),
        aws_access_key_id=settings.get_r2_access_key(),
        aws_secret_access_key=settings.get_r2_secret_key(),
        region_name="auto",
    )


def get_audio_key(challenge_id: str) -> str:
    return f"fake/{challenge_id}.wav"


def get_fake_url(challenge_id: str) -> str:
    """构造 R2 公开访问 URL（使用 public CDN 域名）"""
    public_base = settings.r2_public_base_url.rstrip("/")
    key = get_audio_key(challenge_id)
    return f"{public_base}/{key}"


def upload_raw(key: str, audio_bytes: bytes) -> str:
    """上传原始音频到 R2，返回公开访问 URL（用于 DashScope enrollment）"""
    client = _get_client()
    client.put_object(
        Bucket=settings.get_r2_bucket(),
        Key=key,
        Body=audio_bytes,
        ContentType="audio/wav",
    )
    public_base = settings.r2_public_base_url
    url = f"{public_base}/{key}"
    logger.info(f"已上传原始音频: {key} -> {url}")
    return url


def delete_by_key(key: str) -> bool:
    """按 key 删除 R2 对象"""
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.get_r2_bucket(), Key=key)
        logger.info(f"已删除: {key}")
        return True
    except ClientError as e:
        logger.error(f"删除失败 {key}: {e}")
        return False


def upload_audio(challenge_id: str, audio_bytes: bytes) -> str:
    """上传 fake 音频到 R2，返回公开访问 URL"""
    client = _get_client()
    key = get_audio_key(challenge_id)

    client.put_object(
        Bucket=settings.get_r2_bucket(),
        Key=key,
        Body=audio_bytes,
        ContentType="audio/wav",
        CacheControl="public, max-age=31536000, immutable",
    )
    url = get_fake_url(challenge_id)
    logger.info(f"已上传音频: {key} -> {url}")
    return url


def download_audio(challenge_id: str) -> bytes:
    """从 R2 读取 fake 音频"""
    client = _get_client()
    key = get_audio_key(challenge_id)

    try:
        response = client.get_object(Bucket=settings.get_r2_bucket(), Key=key)
        return response["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise FileNotFoundError(f"音频不存在: {key}")
        raise


def stream_audio(challenge_id: str):
    """流式读取 fake 音频（生成器）"""
    client = _get_client()
    key = get_audio_key(challenge_id)

    try:
        response = client.get_object(Bucket=settings.get_r2_bucket(), Key=key)
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


def delete_audio(challenge_id: str) -> bool:
    """从 R2 删除 fake 音频，返回是否成功"""
    client = _get_client()
    key = get_audio_key(challenge_id)

    try:
        client.delete_object(Bucket=settings.get_r2_bucket(), Key=key)
        logger.info(f"已删除音频: {key}")
        return True
    except ClientError as e:
        logger.error(f"删除音频失败 {key}: {e}")
        return False


def audio_exists(challenge_id: str) -> bool:
    """检查音频是否存在"""
    client = _get_client()
    key = get_audio_key(challenge_id)

    try:
        client.head_object(Bucket=settings.get_r2_bucket(), Key=key)
        return True
    except ClientError:
        return False
