
import logging
import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

logger = logging.getLogger(__name__)
bearer_schema = HTTPBearer()

# Lazy optional Firebase init for backwards compatibility during migration
_firebase_initialized = False
def _init_firebase_if_configured():
    global _firebase_initialized
    if _firebase_initialized:
        return True
    if settings.FIREBASE_CREDENTIALS:
        try:
            import json
            import firebase_admin
            from firebase_admin import credentials
            creds_dict = json.loads(settings.FIREBASE_CREDENTIALS)
            firebase_creds = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(firebase_creds)
            _firebase_initialized = True
            return True
        except Exception as e:
            logger.warning("Firebase init skipped/failed: %s", e)
    return False


def verify_supabase_token(token: str) -> dict:
    """Verify Supabase JWT using SUPABASE_JWT_SECRET (or SECRET_KEY fallback)."""
    secret = settings.SUPABASE_JWT_SECRET or settings.SECRET_KEY
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token missing 'sub' claim")

        app_meta = payload.get("app_metadata", {})
        user_meta = payload.get("user_metadata", {})

        return {
            "uid": user_id,
            "user_id": user_id,
            "sub": user_id,
            "email": payload.get("email"),
            "role": app_meta.get("role") or user_meta.get("role"),
            "claims": payload,
            "user_metadata": user_meta,
            "app_metadata": app_meta,
        }
    except Exception as exc:
        # Fallback to Firebase if Firebase is configured
        if _init_firebase_if_configured():
            try:
                from firebase_admin import auth
                decoded_token = auth.verify_id_token(token)
                return decoded_token
            except Exception:
                pass

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def verify_firebase_token(token: str) -> dict:
    """Delegates to verify_supabase_token for seamless migration."""
    return verify_supabase_token(token)


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer_schema)) -> dict:
    return verify_supabase_token(creds.credentials)


# Backwards compatible alias for existing routes
get_current_firebase_user = get_current_user

 


