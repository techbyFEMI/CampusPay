import re

from pydantic import BaseModel, field_validator


class ProfileResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: str | None
    role: str
    has_transaction_pin: bool


class SetPinRequest(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        pin = v.strip()
        if not re.fullmatch(r"\d{4}", pin):
            raise ValueError("Transaction PIN must be exactly 4 digits (numbers only).")
        return pin
