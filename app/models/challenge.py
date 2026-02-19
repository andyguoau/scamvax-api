from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Challenge(Base):
    """
    id TEXT PRIMARY KEY
    fake_url TEXT NOT NULL
    device_id TEXT  (App 设备 ID，用于频率限制)
    created_at TIMESTAMP DEFAULT NOW()
    """
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fake_url: Mapped[str] = mapped_column(String(512), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
