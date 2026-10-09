import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class wallets(Base):
    __tablename__ = "wallet"
    __table_args__ = (
        CheckConstraint("balance_kobo >= 0", name="ck_wallet_balance_non_negative"),
    )

    wallet_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user.user_id"), unique=True, nullable=False
    )
    balance_kobo: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="NGN", server_default="NGN", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
