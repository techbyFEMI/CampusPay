import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class products(Base):
    __tablename__ = "product"
    __table_args__ = (
        CheckConstraint("price_kobo > 0", name="ck_products_price_positive"),
    )

    product_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    rep_id: Mapped[str] = mapped_column(String, ForeignKey("user.user_id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
