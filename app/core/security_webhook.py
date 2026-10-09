import hashlib
import hmac

from app.core.config import settings


def verify_paystack_signature(raw_payload: bytes, signature_header: str | None) -> bool:
    secret = settings.PAYSTACK_WEBHOOK_SECRET or settings.PAYSTACK_SECRET_KEY
    if not signature_header or not secret:
        return False
    expected = hmac.new(secret.encode(), raw_payload, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature_header)
