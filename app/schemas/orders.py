from pydantic import BaseModel, field_validator


class PlaceOrderRequest(BaseModel):
    rep_id: str
    product_id: str
    pin: str
    idempotency_key: str | None = None

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit() or len(value) != 4:
            raise ValueError("PIN must be exactly 4 digits")
        return value


class PlaceOrderResponse(BaseModel):
    order_id: str
    qr_token: str
    item_price_kobo: int
    fee_kobo: int
    total_charge_kobo: int
    payment_status: str


class ScanQRRequest(BaseModel):
    qr_token: str


class PendingTransactionItem(BaseModel):
    order_id: str
    name: str
    item_price_kobo: int
    fee_kobo: int
    qr_token: str
    payment_status: str
    delivery_status: str
    rep_id: str
    rep_name: str | None = None
    created_at: str


class RepOrderItem(BaseModel):
    order_id: str
    item_description: str
    item_price_kobo: int
    student_name: str
    student_matric: str | None = None
    created_at: str
    payment_status: str
    delivery_status: str
    delivered_at: str | None = None
