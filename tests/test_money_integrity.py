import hashlib
import hmac

from app.core.security_webhook import verify_paystack_signature
from app.models.models import wallets


def test_paystack_signature_verification(monkeypatch):
    signing_key = "paystack-test-signing-value-2026"  # pragma: allowlist secret
    monkeypatch.setattr("app.core.config.settings.PAYSTACK_WEBHOOK_SECRET", signing_key)
    raw_payload = b'{"event":"charge.success","data":{"amount":5000}}'
    signature = hmac.new(signing_key.encode(), raw_payload, hashlib.sha512).hexdigest()

    assert verify_paystack_signature(raw_payload, signature)
    assert not verify_paystack_signature(raw_payload, "incorrect-signature")
    assert not verify_paystack_signature(raw_payload, None)


def test_wallet_stores_exact_integer_kobo():
    wallet = wallets(user_id="student-id", balance_kobo=15_050)

    assert isinstance(wallet.balance_kobo, int)
    assert wallet.balance_kobo == 15_050
