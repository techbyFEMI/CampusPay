import pytest
from unittest.mock import patch
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from main import app
from app.core.security import verify_firebase_token
from app.core.rate_limiter import SimpleRateLimiter, login_rate_limiter, order_rate_limiter, scan_rate_limiter


def test_jwt_signature_bypass_removed():
    """Verify that unverified JWT tokens are strictly rejected and no fallback occurs."""
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiJhdHRhY2tlcl91aWQiLCJyb2xlIjoiQWRtaW4ifQ.fake_signature"  # pragma: allowlist secret

    
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token(invalid_token)
    
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid authentication credentials" in exc_info.value.detail


def test_rate_limiter_exceeded():
    """Verify rate limiter throws HTTP 429 Too Many Requests."""
    limiter = SimpleRateLimiter(requests_per_minute=2)
    
    class MockClient:
        host = "127.0.0.1"
    
    class MockRequest:
        client = MockClient()
    
    req = MockRequest()
    
    # 1st & 2nd request succeed
    limiter(req)
    limiter(req)
    
    # 3rd request triggers 429
    with pytest.raises(HTTPException) as exc_info:
        limiter(req)
    
    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_unauthenticated_protected_endpoint():
    """Verify protected endpoints return HTTP 401 when no token is supplied."""
    client = TestClient(app)
    
    # Wallet endpoint requires auth
    res = client.get("/api/wallet")
    assert res.status_code in (401, 403)

    # Profile endpoint requires auth
    res = client.get("/api/profile")
    assert res.status_code in (401, 403)

