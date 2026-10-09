import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings


bearer_schema = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is required to verify Supabase access tokens")
    if _jwks_client is None:
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def verify_supabase_token(token: str) -> dict:
    """Verify an access token issued by Supabase Auth and return its stable subject."""
    if not settings.SUPABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Auth is not configured.",
        )
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm == "HS256":
            # Legacy Supabase projects can still issue HS256 tokens. Never fall back
            # to the application's general-purpose SECRET_KEY.
            if not settings.SUPABASE_JWT_SECRET:
                raise ValueError("SUPABASE_JWT_SECRET is required for legacy HS256 tokens")
            verification_key = settings.SUPABASE_JWT_SECRET
        elif algorithm in {"RS256", "ES256", "ES384"}:
            verification_key = _get_jwks_client().get_signing_key_from_jwt(token).key
        else:
            raise ValueError("Unsupported Supabase JWT signing algorithm")

        issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
        payload = jwt.decode(
            token,
            verification_key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "role"]},
        )
        if payload.get("role") != "authenticated":
            raise ValueError("Token is not an authenticated-user access token")

        user_id = payload["sub"]
        return {
            "uid": user_id,
            "user_id": user_id,
            "sub": user_id,
            "email": payload.get("email"),
            "claims": payload,
            "user_metadata": payload.get("user_metadata", {}),
            "app_metadata": payload.get("app_metadata", {}),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase access token or expired session.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_schema),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_supabase_token(credentials.credentials)
