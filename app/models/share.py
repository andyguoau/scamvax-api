import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import enum


class ShareStatus(str, enum.Enum):
    active = "active"
    deleted = "deleted"
    failed = "failed"


def generate_share_id() -> str:
    """生成 8 位短链接 ID"""
    return uuid.uuid4().hex[:8]


class Share(Base):
    __tablename__ = "shares"

    share_id: Mapped[str] = mapped_column(
        String(16), primary_key=True, default=generate_share_id
    )
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_clicks: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    status: Mapped[ShareStatus] = mapped_column(
        SAEnum(ShareStatus), default=ShareStatus.active, nullable=False, index=True
    )
    ai_audio_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    script_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.click_count >= self.max_clicks or now >= self.expires_at

    def is_accessible(self) -> bool:
        return self.status == ShareStatus.active and not self.is_expired()
