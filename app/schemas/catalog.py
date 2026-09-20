from pydantic import BaseModel, field_validator
from decimal import Decimal
from datetime import datetime


class VendorSummary(BaseModel):
    
    vendor_id: str
    name: str
    location: str | None
    phone: str | None
    is_open: bool
    cover_image_url: str | None

    model_config = {"from_attributes": True}


class ProductItem(BaseModel):

    product_id: str
    name: str
    description: str | None
    price: Decimal
    is_available: bool
    image_url: str | None = None

    model_config = {"from_attributes": True}


class VendorDetail(BaseModel):
    
    vendor_id: str
    name: str
    location: str | None
    phone: str | None
    is_open: bool
    cover_image_url: str | None
    products: list[ProductItem]

    model_config = {"from_attributes": True}


from pydantic import BaseModel, Field, field_validator


class ProductCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal
    image_url: str | None = Field(default=None, max_length=500)

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Price must be greater than zero")
        return v


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal | None = None
    is_available: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("Price must be greater than zero")
        return v



class ProductResponse(BaseModel):
    product_id: str
    vendor_id: str
    name: str
    description: str | None
    price: Decimal
    is_available: bool
    image_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
