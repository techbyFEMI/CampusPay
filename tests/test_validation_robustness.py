import pytest
from pydantic import ValidationError

from app.schemas.catalog import ProductCreateRequest, ProductUpdateRequest
from app.schemas.orders import PlaceOrderRequest
from app.schemas.profile import SetPinRequest
from app.main import origins, app
from fastapi.testclient import TestClient


def test_product_price_kobo_validation():
    """Verify catalog prices are positive integer kobo amounts."""
    with pytest.raises(ValidationError):
        ProductCreateRequest(name="Test Item", price_kobo=0)

    with pytest.raises(ValidationError):
        ProductCreateRequest(name="Test Item", price_kobo=-1050)

    product = ProductCreateRequest(name="Valid Item", price_kobo=50_000)
    assert product.price_kobo == 50_000


def test_pin_format_validation():
    """Verify PIN must be exactly 4 numeric digits."""
    with pytest.raises(ValidationError):
        SetPinRequest(pin="123")  # Too short

    with pytest.raises(ValidationError):
        SetPinRequest(pin="abcd")  # Non-numeric

    with pytest.raises(ValidationError):
        SetPinRequest(pin="12345")  # Too long

    valid_pin = SetPinRequest(pin=" 9876 ")
    assert valid_pin.pin == "9876"


def test_cors_origins_whitelist():
    """Verify CORS origins use explicit whitelist and do not include wildcard '*'."""
    assert "*" not in origins
    assert any("vercel.app" in o or "onrender.com" in o for o in origins)


def test_health_check_sanitization():
    """Verify health endpoint does not leak raw database exception strings."""
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    # Ensure no raw tracebacks or SQL queries in response
    if "database_error" in data:
        assert data["database_error"] == "Database connection error"
