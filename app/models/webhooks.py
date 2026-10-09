from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import JSON_TYPE, hookstate


class webhook_events(Base):
    __tablename__ = "provider_webhook_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[hookstate] = mapped_column(SAEnum(hookstate), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
