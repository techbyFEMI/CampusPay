from pydantic import BaseModel, field_validator
from datetime import datetime


class PlaceOrderRequest(BaseModel):
    rep_id: str
    product_id: str               # All orders must reference a catalog product
    pin: str
    idempotency_key: str | None = None

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 4:
            raise ValueError("PIN must be exactly 4 digits")
        return v


class PlaceOrderResponse(BaseModel):
    order_id: str
    qr_token: str
    timer_expires_at: datetime
    total_charged: str


class ScanQRRequest(BaseModel):
    qr_token: str


class PendingTransactionItem(BaseModel):
    order_id: str
    name: str
    price: str
    description: str | None = None
    location: str | None = None
    image_url: str | None = None
    status: str = "confirmed"
    qr_token: str
    rep_id: str
    rep_name: str | None = None
    total_charged: str
    timer_expire_at: str
    is_collected: bool = False
    created_at: str


class RepOrderItem(BaseModel):
    order_id: str
    item_description: str
    item_amount: str
    student_name: str
    student_matric: str | None = None
    created_at: str
    order_status: str
    is_collected: bool
    collected_at: str | None = None
