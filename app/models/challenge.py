from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Challenge(Base):
    """
    极简表结构，对应指令要求：
    id TEXT PRIMARY KEY
    fake_url TEXT NOT NULL
    created_at TIMESTAMP DEFAULT NOW()
    """
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fake_url: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
