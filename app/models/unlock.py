from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class DeviceWallet(Base):
    __tablename__ = "device_wallets"

    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    bonus_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UnlockTokenUse(Base):
    __tablename__ = "unlock_token_uses"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
