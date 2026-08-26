import pytest
import sqlite3
import json
from backend.app.audit_store import CryptographicAuditLedger, GENESIS_HASH

def test_audit_hash_chain_creation_and_continuity(tmp_path):
    db_file = str(tmp_path / "test_chain.db")
    ledger = CryptographicAuditLedger(db_path=db_file)

    # 1. Initially empty ledger must be valid
    initial_verify = ledger.verify_chain_integrity()
    assert initial_verify["valid"] is True
    assert initial_verify["total_events"] == 0

    # 2. Append Event 1
    e1 = ledger.record_event(
        trace_id="tr_101",
        merchant_id="m_01",
        payment_id="pay_01",
        event_type="payment.failed",
        failure_class="TRANSIENT_GATEWAY",
        decision={"strategy": "DELAYED_RETRY"},
        policy_verdict="ALLOWED",
        action_taken="SCHEDULE_MANDATE_RETRY"
    )
    assert e1["prev_hash"] == GENESIS_HASH
    assert len(e1["current_hash"]) == 64

    # 3. Append Event 2
    e2 = ledger.record_event(
        trace_id="tr_102",
        merchant_id="m_01",
        payment_id="pay_02",
        event_type="payment.failed",
        failure_class="INSUFFICIENT_FUNDS",
        decision={"strategy": "DISPATCH_PAYMENT_LINK"},
        policy_verdict="ALLOWED",
        action_taken="CREATE_1CLICK_PAYMENT_LINK"
    )
    # Event 2's prev_hash must strictly equal Event 1's current_hash
    assert e2["prev_hash"] == e1["current_hash"]

    # 4. Verify chain integrity across both blocks
    verify_res = ledger.verify_chain_integrity()
    assert verify_res["valid"] is True
    assert verify_res["total_events"] == 2
    assert verify_res["tampering_detected"] is False

def test_audit_tampering_detection(tmp_path):
    db_file = str(tmp_path / "test_tamper.db")
    ledger = CryptographicAuditLedger(db_path=db_file)

    # Add 3 legitimate events
    for i in range(3):
        ledger.record_event(
            trace_id=f"tr_{i}",
            merchant_id="m_01",
            payment_id=f"pay_{i}",
            event_type="payment.failed",
            failure_class="TRANSIENT_GATEWAY",
            decision={"step": i},
            policy_verdict="ALLOWED",
            action_taken="ACTION"
        )

    # Confirm valid before tampering
    assert ledger.verify_chain_integrity()["valid"] is True

    # Malicious direct DB modification of block 2 payload
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("UPDATE audit_chain_ledger SET decision_json = ? WHERE sequence_id = 2", (json.dumps({"HACKED": True}),))
    conn.close()

    # Verification must catch the tampering immediately
    tampered_verify = ledger.verify_chain_integrity()
    assert tampered_verify["valid"] is False
    assert tampered_verify["tampering_detected"] is True
    assert tampered_verify["broken_at_sequence"] == 2
