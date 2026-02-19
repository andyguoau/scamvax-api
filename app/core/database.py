from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

# Render 注入的 DATABASE_URL 是 postgresql:// 开头，需要换成 asyncpg 驱动
_db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    _db_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """创建所有表，并补齐缺失的列（幂等，可重复运行）"""
    async with engine.begin() as conn:
        from app.models import share  # noqa: F401
        from app.models import challenge  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

        # 补齐 device_id 列（老数据库可能没有）
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE challenges ADD COLUMN IF NOT EXISTS device_id VARCHAR(64)"
            )
        )
