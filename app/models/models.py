from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    Text,
    DateTime,
    Numeric,
    Boolean,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal
from app.core.database import Base
from enum import Enum
from datetime import datetime, timezone, timedelta
from sqlalchemy import Enum as SAEnum
import uuid


class approles(Enum):
    Rep = "Rep"
    Student = "Student"
    Admin = "Admin"


class departments(Base):
    __tablename__ = "department"

    department_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class rosters(Base):
    __tablename__ = "roster"

    roster_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("department.department_id"),
        index=True,
    )
    matric_number: Mapped[str] = mapped_column(String, index=True)
    full_name: Mapped[str] = mapped_column(String)
    is_claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class payoutstat(Enum):
    not_attempted = "not_attempted"
    success = "success"
    failed = "failed"
    

class accstatus(Enum):
    active = "Active"
    suspended = "Suspended"


class hookstate(Enum):
    processed = "Processed"
    failed = "Failed"
    duplicate = "Duplicate"


class orderstat(Enum):
    pending = "Pending"
    confirmed = "Confirmed"
    expired = "Expired"
    refunded = "Refunded"


class users(Base):

    __tablename__ = "user"

    user_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    firebase_uid: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    matric_number: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    department_id: Mapped[str | None] = mapped_column(String, ForeignKey("department.department_id"), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[approles] = mapped_column(SAEnum(approles))
    full_name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    vendor_bank_account: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    vendor_bank_code: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    vendor_bank_name: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    transaction_pin_hash: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    failed_pin_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    pin_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    vendor_location: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    vendor_is_open: Mapped[bool] = mapped_column(
        Boolean,
        server_default="false",
        default=False,
    )

    vendor_cover_image_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class accounts(Base):

    __tablename__ = "account"

    dva_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    student_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("user.user_id"),
    )

    account_reference: Mapped[str] = mapped_column(Text, unique=True)
    bank_account_number: Mapped[str] = mapped_column(Text)
    bank_name: Mapped[str] = mapped_column(Text)

    status: Mapped[accstatus] = mapped_column(SAEnum(accstatus))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class wallets(Base):

    __tablename__ = "wallet"
    __table_args__ = (
        CheckConstraint("available_balance >= 0", name="ck_wallets_available_balance_non_negative"),
        CheckConstraint("locked_balance >= 0", name="ck_wallets_locked_balance_non_negative"),
    )

    wallet_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("user.user_id"),
        unique=True,
    )

    available_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    locked_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class webhook_events(Base):

    __tablename__ = "webhookEvents"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String)
    account_reference: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[hookstate] = mapped_column(SAEnum(hookstate))
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class orders(Base):

    __tablename__ = "order"
    __table_args__ = (
        CheckConstraint("item_amount > 0", name="ck_orders_item_amount_positive"),
    )

    order_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String,
        unique=True,
        index=True,
        nullable=True,
    )

    student_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("user.user_id"),
    )

    vendor_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("user.user_id"),
    )

    item_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    order_status: Mapped[orderstat] = mapped_column(SAEnum(orderstat))



    qr_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    timer_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(hours=24),
    )

    nomba_transfer_ref: Mapped[str | None] = mapped_column(String)
    penalty_status: Mapped[str | None] = mapped_column(String, nullable=True)
    penalty_transfer_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    
    payout_status: Mapped[payoutstat] = mapped_column(
        SAEnum(payoutstat, name="payoutstat"),
        default=payoutstat.not_attempted,
        server_default=payoutstat.not_attempted.value,
        nullable=False,
    )
    payout_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payout_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    is_collected: Mapped[bool] = mapped_column(
        Boolean,
        server_default="false",
        default=False,
    )
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

class products(Base):

    __tablename__ = "product"

    product_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    vendor_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("user.user_id"),
    )

    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    image_url: Mapped[str | None] = mapped_column(String, nullable=True)

    is_available: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class wallet_ledger(Base):
    
    __tablename__ = "wallet_ledger"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_wallet_ledger_amount_positive"),
    )

    ledger_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    wallet_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("wallet.wallet_id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("user.user_id"),
        nullable=False,
        index=True,
    )

    direction: Mapped[str] = mapped_column(String(6), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    balance_before: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    reference: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String, nullable=True)

    reason: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )