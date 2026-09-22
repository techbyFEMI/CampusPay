import jwt
import pytest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, status

from app.core.security import verify_supabase_token, get_current_user


def test_supabase_jwt_verification(monkeypatch):
    test_secret = "test_supabase_jwt_secret_key_12345"  # pragma: allowlist secret
    monkeypatch.setattr("app.core.config.settings.SUPABASE_JWT_SECRET", test_secret)


    now = datetime.now(timezone.utc)
    payload = {
        "sub": "usr_supabase_uuid_12345",
        "email": "student@campuspay.edu",
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "app_metadata": {"role": "Student"},
        "user_metadata": {"full_name": "Test Student"},
    }

    token = jwt.encode(payload, test_secret, algorithm="HS256")

    user = verify_supabase_token(token)
    assert user["uid"] == "usr_supabase_uuid_12345"
    assert user["email"] == "student@campuspay.edu"
    assert user["role"] == "Student"


def test_supabase_expired_jwt(monkeypatch):
    test_secret = "test_supabase_jwt_secret_key_12345"  # pragma: allowlist secret
    monkeypatch.setattr("app.core.config.settings.SUPABASE_JWT_SECRET", test_secret)


    past = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "sub": "usr_supabase_uuid_12345",
        "email": "student@campuspay.edu",
        "exp": int(past.timestamp()),
    }

    stale_token = jwt.encode(payload, test_secret, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(stale_token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
