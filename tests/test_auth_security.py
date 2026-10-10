import time

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.core.rate_limiter import SimpleRateLimiter
from app.core.security import verify_supabase_token
from app.main import app


def test_supabase_rejects_invalid_access_token(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(
        "app.core.config.settings.SUPABASE_JWT_SECRET",
        "test-supabase-jwt-secret-with-safe-length",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token("not-a-valid-jwt")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_supabase_rejects_wrong_signature(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(
        "app.core.config.settings.SUPABASE_JWT_SECRET",
        "expected-supabase-jwt-secret-with-safe-length",
    )
    token = jwt.encode(
        {
            "sub": "student-id",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        },
        "different-supabase-jwt-secret-with-safe-length",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_rate_limiter_exceeded():
    limiter = SimpleRateLimiter(requests_per_minute=2)

    class MockClient:
        host = "127.0.0.1"

    class MockRequest:
        client = MockClient()

    request = MockRequest()
    limiter(request)
    limiter(request)

    with pytest.raises(HTTPException) as exc_info:
        limiter(request)

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_unauthenticated_protected_endpoints_return_401():
    client = TestClient(app)

    assert client.get("/api/wallet").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.get("/api/profile").status_code == status.HTTP_401_UNAUTHORIZED
