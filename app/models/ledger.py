import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import accounttype, entrytype


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        UniqueConstraint(
            "account_type", "user_id", "currency", name="uq_ledger_account_owner_type_currency"
        ),
    )

    account_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    account_type: Mapped[accounttype] = mapped_column(
        SAEnum(accounttype), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.user_id"), nullable=True
    )
    balance_kobo: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="NGN", server_default="NGN", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Journal(Base):
    __tablename__ = "journals"
    __table_args__ = (
        UniqueConstraint("reference", name="uq_journals_reference"),
    )

    journal_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    reference: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint("amount_kobo > 0", name="ck_journal_entries_amount_positive"),
    )

    entry_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    journal_id: Mapped[str] = mapped_column(
        String, ForeignKey("journals.journal_id"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("ledger_accounts.account_id"), nullable=False
    )
    entry_type: Mapped[entrytype] = mapped_column(SAEnum(entrytype), nullable=False)
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
