import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import deliverystat, paymentstat, transferattemptstat


class orders(Base):
    __tablename__ = "order"
    __table_args__ = (
        CheckConstraint("item_price_kobo > 0", name="ck_orders_item_price_positive"),
        CheckConstraint("fee_kobo >= 0 AND fee_kobo <= 5000", name="ck_orders_fee_range"),
        CheckConstraint("provider_cost_kobo >= 0", name="ck_orders_provider_cost_non_negative"),
        CheckConstraint(
            "rep_share_kobo >= 0 AND campuspay_share_kobo >= 0",
            name="ck_orders_shares_non_negative",
        ),
        CheckConstraint(
            "rep_share_kobo + campuspay_share_kobo <= fee_kobo",
            name="ck_orders_shares_within_fee",
        ),
    )

    order_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    student_id: Mapped[str] = mapped_column(String, ForeignKey("user.user_id"), index=True)
    rep_id: Mapped[str] = mapped_column(String, ForeignKey("user.user_id"), index=True)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("product.product_id"))
    item_description: Mapped[str] = mapped_column(String, nullable=False)
    item_price_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rep_share_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campuspay_share_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider_cost_kobo: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    payment_status: Mapped[paymentstat] = mapped_column(
        SAEnum(paymentstat, name="paymentstat"),
        default=paymentstat.pending,
        server_default=paymentstat.pending.value,
        nullable=False,
    )
    delivery_status: Mapped[deliverystat] = mapped_column(
        SAEnum(deliverystat, name="deliverystat"),
        default=deliverystat.awaiting_delivery,
        server_default=deliverystat.awaiting_delivery.value,
        nullable=False,
    )
    qr_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TransferAttempt(Base):
    __tablename__ = "transfer_attempts"
    __table_args__ = (
        UniqueConstraint("order_id", "attempt_number", name="uq_transfer_attempt_order_number"),
        UniqueConstraint("provider_reference", name="uq_transfer_attempt_provider_ref"),
        CheckConstraint("attempt_number BETWEEN 1 AND 3", name="ck_transfer_attempt_number_range"),
        CheckConstraint("status IN ('pending', 'success', 'failed')", name="ck_transfer_attempt_status_valid"),
    )

    transfer_attempt_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    order_id: Mapped[str] = mapped_column(
        String, ForeignKey("order.order_id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[transferattemptstat] = mapped_column(
        SAEnum(transferattemptstat, name="transferattemptstat"), nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
