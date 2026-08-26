import hmac
import hashlib
import pytest
import concurrent.futures
from backend.app.security import verify_razorpay_signature, DistributedIdempotencyStore
from backend.app.audit_store import AuditStore

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

def test_distributed_idempotency_mutex(tmp_path):
    db_file = str(tmp_path / "test_idempotency.db")
    store = DistributedIdempotencyStore(db_path=db_file)
    
    key = "pay_test_unique_001"
    
    # First acquisition must succeed
    assert store.acquire_lock(key) is True
    
    # Second immediate acquisition on same key must fail
    assert store.acquire_lock(key) is False

def test_high_concurrency_race_condition(tmp_path):
    """
    Stress-test: 50 concurrent worker threads attempting to acquire the same payment lock simultaneously.
    Mathematically, exactly ONE thread must win, and 49 must be rejected.
    """
    db_file = str(tmp_path / "test_concurrency.db")
    store = DistributedIdempotencyStore(db_path=db_file)
    
    key = "pay_concurrent_storm_123"
    
    def try_lock(_):
        return store.acquire_lock(key)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(try_lock, range(50)))
        
    success_count = sum(1 for r in results if r is True)
    failure_count = sum(1 for r in results if r is False)
    
    assert success_count == 1
    assert failure_count == 49

def test_audit_store_logging(tmp_path):
    db_file = str(tmp_path / "test_audit.db")
    store = AuditStore(db_path=db_file)
    
    evt_id = store.record_event(
        payment_id="pay_sample_123",
        event_type="payment.failed",
        policy_passed=True,
        action_taken="DISPATCHED_UPI_LINK",
        recovery_status="SUCCESS",
        raw_error_code="INSUFFICIENT_FUNDS",
        failure_category="SOFT_DECLINE",
        confidence_score=0.95,
        metadata={"amount": 999.0}
    )
    
    assert evt_id.startswith("evt_")
    events = store.get_events()
    assert len(events) == 1
    assert events[0]["payment_id"] == "pay_sample_123"
    assert events[0]["action_taken"] == "DISPATCHED_UPI_LINK"
