import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.database import AsyncSessionLocal
from app.services.share import cleanup_expired_shares

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _cleanup_job():
    async with AsyncSessionLocal() as db:
        count = await cleanup_expired_shares(db)
        if count:
            logger.info(f"[定时任务] 清理了 {count} 个过期 share")


def start_scheduler():
    scheduler.add_job(
        _cleanup_job,
        trigger=IntervalTrigger(minutes=30),
        id="cleanup_expired_shares",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("定时清理任务已启动（每 30 分钟）")


def stop_scheduler():
    scheduler.shutdown(wait=False)
    logger.info("定时清理任务已停止")
