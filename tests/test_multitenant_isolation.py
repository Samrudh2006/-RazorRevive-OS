import pytest
import time
from backend.app.security import DistributedIdempotencyStore
from backend.app.audit_store import CryptographicAuditLedger

def test_multitenant_idempotency_isolation():
    store = DistributedIdempotencyStore()
    pay_key = f"idem_multi_{int(time.time())}"
    
    # Merchant A acquires lock on key
    res_a = store.acquire_lock(pay_key, payload_hash="hash_a", merchant_id="merchant_alpha")
    assert res_a is True
    
    # Check execution record contains merchant_api_key_id
    rec = store.get_execution_record(pay_key)
    assert rec is not None
    assert rec["merchant_api_key_id"] == "merchant_alpha"
    
    # Complete execution
    store.mark_completed(pay_key, result_payload={"recovered": True})
    assert store.is_execution_completed(pay_key) is True

def test_multitenant_audit_ledger_recording():
    audit = CryptographicAuditLedger()
    evt = audit.record_event(
        trace_id="tr_multi_01",
        merchant_id="merchant_beta",
        payment_id="pay_multi_100",
        event_type="PAYMENT_RECOVERY",
        failure_class="TRANSIENT_GATEWAY",
        decision={"retry": 15},
        policy_verdict="ALLOWED",
        action_taken="DISPATCH_LINK"
    )
    assert evt["current_hash"] is not None
    
    # Verify cryptographic integrity still passes
    verify_res = audit.verify_chain_integrity()
    assert verify_res["valid"] is True
    assert verify_res["tampering_detected"] is False
