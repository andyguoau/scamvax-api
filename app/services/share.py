import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from app.core.config import get_settings
from app.models.share import Share, ShareStatus, generate_share_id
from app.services import storage

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── 创建 ────────────────────────────────────────────────────────────────────

async def create_share(
    db: AsyncSession,
    device_id: str,
    ai_audio_bytes: bytes,
    lang: str = "zh",
    platform: str | None = None,
    region: str | None = None,
) -> Share:
    """
    创建新 Share：
    1. 生成 share_id
    2. 上传 AI 音频到 R2
    3. 写入数据库
    """
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.share_ttl_hours)

    for attempt in range(3):
        share_id = generate_share_id()

        # 上传音频（先传，传失败就不写 DB）
        try:
            audio_key = await run_in_threadpool(storage.upload_audio, share_id, ai_audio_bytes)
        except Exception as e:
            logger.error(f"音频上传失败: {e}")
            raise

        share = Share(
            share_id=share_id,
            device_id=device_id,
            expires_at=expires_at,
            click_count=0,
            max_clicks=settings.share_max_clicks,
            status=ShareStatus.active,
            ai_audio_key=audio_key,
            lang=lang,
            platform=platform,
            region=region,
            script_version="v1",
        )
        db.add(share)
        try:
            await db.commit()
            await db.refresh(share)
            return share
        except IntegrityError:
            await db.rollback()
            await run_in_threadpool(storage.delete_audio, share_id)
            if attempt == 2:
                raise RuntimeError("share_id 冲突，无法创建 Share，请重试")
            logger.warning(f"share_id 冲突，重新生成 (attempt {attempt + 1})")


# ─── 访问（计数 + 过期检查） ────────────────────────────────────────────────

async def access_share(db: AsyncSession, share_id: str) -> Share | None:
    """
    访问 share：
    - 原子性递增 click_count
    - 检查是否过期
    - 若过期，触发销毁并返回 None
    """
    # 原子性 UPDATE + 获取最新数据（防并发竞态）
    stmt = (
        update(Share)
        .where(
            and_(
                Share.share_id == share_id,
                Share.status == ShareStatus.active,
            )
        )
        .values(click_count=Share.click_count + 1)
        .returning(Share)
    )
    result = await db.execute(stmt)
    await db.commit()
    share = result.scalars().first()

    if share is None:
        # share 不存在或已删除
        return None

    # 检查是否已过期
    if share.is_expired():
        logger.info(f"Share {share_id} 已过期，触发销毁")
        await delete_share(db, share_id)
        return None

    return share


async def get_share(db: AsyncSession, share_id: str) -> Share | None:
    """不计数，仅查询（用于音频接口）"""
    result = await db.execute(
        select(Share).where(Share.share_id == share_id)
    )
    return result.scalars().first()


# ─── 销毁 ────────────────────────────────────────────────────────────────────

async def delete_share(db: AsyncSession, share_id: str) -> bool:
    """
    完整销毁流程：
    1. 删除 R2 音频
    2. 更新 DB status = deleted
    """
    # 删除 R2 音频
    audio_deleted = await run_in_threadpool(storage.delete_audio, share_id)
    if not audio_deleted:
        logger.warning(f"R2 音频删除失败或不存在: {share_id}")

    # 更新 DB
    stmt = (
        update(Share)
        .where(Share.share_id == share_id)
        .values(status=ShareStatus.deleted)
    )
    await db.execute(stmt)
    await db.commit()

    logger.info(f"Share {share_id} 已完整销毁")
    return True


async def mark_failed(db: AsyncSession, share_id: str) -> None:
    """标记为失败（生成过程异常回滚用）"""
    stmt = (
        update(Share)
        .where(Share.share_id == share_id)
        .values(status=ShareStatus.failed)
    )
    await db.execute(stmt)
    await db.commit()


# ─── 定时清理 ────────────────────────────────────────────────────────────────

async def cleanup_expired_shares(db: AsyncSession) -> int:
    """
    定时任务：扫描并销毁所有过期的 active share
    返回清理数量
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Share).where(
            and_(
                Share.status == ShareStatus.active,
                Share.expires_at <= now,
            )
        )
    )
    expired = result.scalars().all()

    count = 0
    for share in expired:
        await delete_share(db, share.share_id)
        count += 1

    if count:
        logger.info(f"定时清理：销毁了 {count} 个过期 share")
    return count


# ─── 频率限制检查 ────────────────────────────────────────────────────────────

async def check_rate_limit(db: AsyncSession, device_id: str) -> bool:
    """
    检查设备在时间窗口内的创建次数
    返回 True = 允许；False = 超限
    """
    window_start = datetime.now(timezone.utc) - timedelta(
        seconds=settings.rate_limit_window_seconds
    )
    result = await db.execute(
        select(Share).where(
            and_(
                Share.device_id == device_id,
                Share.created_at >= window_start,
                Share.status != ShareStatus.failed,
            )
        )
    )
    recent_count = len(result.scalars().all())
    return recent_count < settings.rate_limit_per_device
