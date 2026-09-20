import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

from app.core.security_webhook import verify_nomba_signature, is_timestamp_valid
from app.models.models import wallets, orders, wallet_ledger, users


def test_timestamp_validity():
    now_utc = datetime.now(timezone.utc)
    
    # Fresh timestamp (now) -> True
    assert is_timestamp_valid(str(now_utc.timestamp())) is True
    
    # 2 minutes ago -> True
    two_min_ago = (now_utc - timedelta(minutes=2)).timestamp()
    assert is_timestamp_valid(str(two_min_ago)) is True
    
    # 10 minutes ago (replay attack) -> False
    ten_min_ago = (now_utc - timedelta(minutes=10)).timestamp()
    assert is_timestamp_valid(str(ten_min_ago)) is False
    
    # Invalid string -> False
    assert is_timestamp_valid("invalid-timestamp") is False


def test_nomba_signature_verification(monkeypatch):
    # Set mock secret
    monkeypatch.setattr("app.core.security_webhook.NOMBA_WEBHOOK_SECRET", "test_secret_123")
    
    now_ts = str(datetime.now(timezone.utc).timestamp())
    payload_dict = {
        "event_type": "payment_success",
        "requestId": "req_123456",
        "data": {
            "merchant": {"userId": "user_1", "walletId": "w_1"},
            "transaction": {
                "transactionId": "tx_1",
                "type": "deposit",
                "time": "2026-09-19 20:00:00",
                "responseCode": "00"
            }
        }
    }
    raw_payload = json.dumps(payload_dict)
    
    hashing_payload = f"payment_success:req_123456:user_1:w_1:tx_1:deposit:2026-09-19 20:00:00:00:{now_ts}"
    digest = hmac.new(b"test_secret_123", hashing_payload.encode(), hashlib.sha256).digest()
    valid_sig = base64.b64encode(digest).decode()
    
    # Valid signature and timestamp
    assert verify_nomba_signature(raw_payload, valid_sig, now_ts) is True
    
    # Invalid signature header
    assert verify_nomba_signature(raw_payload, "invalid_sig", now_ts) is False
    
    # Stale timestamp (10 minutes old) with otherwise valid signature
    stale_ts = str((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
    assert verify_nomba_signature(raw_payload, valid_sig, stale_ts) is False


def test_wallet_model_decimal_precision():
    w = wallets(
        wallet_id="w_test",
        user_id="u_test",
        available_balance=Decimal("150.50"),
        locked_balance=Decimal("0.00"),
        currency="NGN"
    )
    assert isinstance(w.available_balance, Decimal)
    assert w.available_balance == Decimal("150.50")
