import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import accstatus, approles, kycstat


class departments(Base):
    __tablename__ = "department"

    department_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class rosters(Base):
    __tablename__ = "roster"

    roster_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    department_id: Mapped[str] = mapped_column(
        String, ForeignKey("department.department_id"), index=True
    )
    matric_number: Mapped[str] = mapped_column(String, index=True)
    full_name: Mapped[str] = mapped_column(String)
    is_claimed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class users(Base):
    __tablename__ = "user"

    user_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Supabase Auth subject. This is also the canonical CampusPay user ID.
    matric_number: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("department.department_id"), nullable=True
    )
    role: Mapped[approles] = mapped_column(SAEnum(approles))
    full_name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    nin_verification_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    nin_verification_status: Mapped[kycstat | None] = mapped_column(
        SAEnum(kycstat), nullable=True
    )
    nin_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nin_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bvn_verification_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    bvn_verification_status: Mapped[kycstat | None] = mapped_column(
        SAEnum(kycstat), nullable=True
    )
    bvn_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bvn_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)

    transaction_pin_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    failed_pin_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    pin_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    rep_location: Mapped[str | None] = mapped_column(String, nullable=True)
    rep_is_open: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False
    )
    rep_cover_image_url: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class accounts(Base):
    __tablename__ = "account"

    dva_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user.user_id"), unique=True, index=True
    )
    account_reference: Mapped[str] = mapped_column(Text, unique=True)
    provider_customer_code: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    provider_dva_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    bank_account_number: Mapped[str] = mapped_column(Text)
    bank_name: Mapped[str] = mapped_column(Text)
    status: Mapped[accstatus] = mapped_column(SAEnum(accstatus))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
