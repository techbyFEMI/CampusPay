from pydantic import BaseModel, field_validator, model_validator
from decimal import Decimal
from datetime import datetime


class PlaceOrderRequest(BaseModel):
    rep_id: str | None = None
    vendor_id: str | None = None  # Alias for rep_id for backward compatibility
    item_description: str
    item_amount: Decimal
    pin: str

    @model_validator(mode="after")
    def check_rep_or_vendor_id(self):
        if not self.rep_id and not self.vendor_id:
            raise ValueError("rep_id is required")
        if not self.rep_id and self.vendor_id:
            self.rep_id = self.vendor_id
        return self

    @field_validator("item_amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("item_amount must be greater than zero")
        return v

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
