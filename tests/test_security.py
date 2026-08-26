import hmac
import hashlib
import time
import uuid
import pytest
import concurrent.futures
from backend.app.security import verify_razorpay_signature, DistributedIdempotencyStore, mask_pii_string
from backend.app.audit_store import CryptographicAuditLedger, GENESIS_HASH

def test_hmac_signature_verification():
    secret = "test_webhook_secret_123"
    raw_payload = b'{"event":"payment.failed","id":"pay_test_999"}'
    
    valid_sig = hmac.new(secret.encode(), raw_payload, hashlib.sha256).hexdigest()
    assert verify_razorpay_signature(raw_payload, valid_sig, secret=secret) is True

    # Tampered payload
    tampered_payload = b'{"event":"payment.failed","id":"pay_test_HACKED"}'
    assert verify_razorpay_signature(tampered_payload, valid_sig, secret=secret) is False

    # Invalid signature
    assert verify_razorpay_signature(raw_payload, "invalid_sig_abc", secret=secret) is False
    assert verify_razorpay_signature(raw_payload, None, secret=secret) is False

def test_replay_attack_prevention():
    secret = "test_secret_321"
    raw_payload = b'{"event":"payment.failed"}'
    valid_sig = hmac.new(secret.encode(), raw_payload, hashlib.sha256).hexdigest()
    
    # Fresh timestamp -> PASS
    now = int(time.time())
    assert verify_razorpay_signature(raw_payload, valid_sig, secret=secret, timestamp=now) is True

    # Expired replay timestamp (10 minutes in past > 300s) -> REJECT
    old_timestamp = now - 600
    assert verify_razorpay_signature(raw_payload, valid_sig, secret=secret, timestamp=old_timestamp) is False

def test_pii_masking_compliance():
    phone = "+919876543210"
    masked_phone = mask_pii_string(phone)
    assert "987654" not in masked_phone
    assert masked_phone.startswith("+919")
    assert masked_phone.endswith("10")

    email = "customer@example.com"
    masked_email = mask_pii_string(email)
    assert "@example.com" in masked_email
    assert "customer" not in masked_email

def test_distributed_idempotency_mutex(tmp_path):
    db_file = str(tmp_path / f"test_idempotency_{uuid.uuid4().hex[:8]}.db")
    store = DistributedIdempotencyStore(db_path=db_file)
    
    key = f"pay_test_unique_{uuid.uuid4().hex[:8]}"
    assert store.acquire_lock(key) is True
    assert store.acquire_lock(key) is False

def test_high_concurrency_race_condition(tmp_path):
    db_file = str(tmp_path / f"test_concurrency_{uuid.uuid4().hex[:8]}.db")
    store = DistributedIdempotencyStore(db_path=db_file)
    
    key = f"pay_concurrent_storm_{uuid.uuid4().hex[:8]}"
    
    def try_lock(_):
        return store.acquire_lock(key)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(try_lock, range(50)))
        
    assert sum(1 for r in results if r is True) == 1
    assert sum(1 for r in results if r is False) == 49

def test_audit_store_logging(tmp_path):
    db_file = str(tmp_path / f"test_audit_{uuid.uuid4().hex[:8]}.db")
    store = CryptographicAuditLedger(db_path=db_file)
    
    res = store.record_event(
        trace_id="tr_sample",
        merchant_id="m_01",
        payment_id="pay_sample_123",
        event_type="payment.failed",
        failure_class="INSUFFICIENT_FUNDS",
        decision={"action": "DISPATCH_PAYMENT_LINK"},
        policy_verdict="ALLOWED",
        action_taken="DISPATCHED_UPI_LINK"
    )
    
    assert res["event_id"].startswith("evt_")
    events = store.get_events()
    assert len(events) == 1
    assert events[0]["payment_id"] == "pay_sample_123"
