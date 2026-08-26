import time
import pytest
import concurrent.futures
import uuid
from pydantic import ValidationError

from backend.app.security import verify_razorpay_signature, DistributedIdempotencyStore
from backend.app.diagnostic_engine import DiagnosticEngine
from backend.app.policy_engine import PolicyEngine
from backend.app.schemas import DiagnosisProposal
from backend.app.b2b.state_machine import B2BReceivablesStateMachine
from backend.app.b2b.voice_agent import B2BVoiceDialogueEngine, VoiceDialogueTurnRequest

def test_attack_01_duplicate_webhook_storm(tmp_path):
    """50 concurrent worker threads attempting to process the exact same webhook."""
    db_file = str(tmp_path / f"test_storm_{uuid.uuid4().hex[:8]}.db")
    store = DistributedIdempotencyStore(db_path=db_file)
    key = "wh_storm_pay_999"
    
    def worker(_):
        return store.acquire_lock(key)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(worker, range(50)))

    assert sum(1 for r in results if r is True) == 1
    assert sum(1 for r in results if r is False) == 49

def test_attack_02_tampered_hmac():
    secret = "secret_key"
    payload = b'{"amount": 1000}'
    import hmac, hashlib
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    tampered_payload = b'{"amount": 100000}'
    assert verify_razorpay_signature(tampered_payload, sig, secret=secret) is False

def test_attack_03_missing_hmac():
    assert verify_razorpay_signature(b'{"test": 1}', None, secret="secret") is False

def test_attack_04_expired_replay_timestamp():
    secret = "secret_key"
    payload = b'{"event": "payment.failed"}'
    import hmac, hashlib
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    now = int(time.time())
    assert verify_razorpay_signature(payload, sig, secret=secret, timestamp=now) is True
    # 600s in past (> 300s window) -> Must be rejected
    assert verify_razorpay_signature(payload, sig, secret=secret, timestamp=now - 600) is False

def test_attack_05_negative_amount_schema_rejection():
    with pytest.raises(ValidationError):
        DiagnosisProposal(
            payment_id="pay_neg_01",
            amount=-500.0, # Negative amount prohibited
            raw_error_code="GATEWAY_ERROR",
            failure_class="TRANSIENT_GATEWAY",
            confidence=0.9,
            recommended_strategy="DELAYED_RETRY",
            diagnostic_summary="Negative amount attack"
        )

def test_attack_06_low_confidence_suppression():
    diag = DiagnosisProposal(
        payment_id="pay_low_01",
        amount=1000.0,
        raw_error_code="UNKNOWN",
        failure_class="ABANDONED_AUTH",
        confidence=0.40, # < 0.60 threshold
        recommended_strategy="DISPATCH_PAYMENT_LINK",
        diagnostic_summary="Low confidence test"
    )
    verdict = PolicyEngine.evaluate(diagnosis=diag, attempt_count=1)
    assert verdict.passed_all_gates is False
    assert verdict.verdict == "SUPPRESSED"

def test_attack_07_high_value_anomaly_escalation():
    diag = DiagnosisProposal(
        payment_id="pay_high_01",
        amount=75000.0, # > 50,000 threshold
        raw_error_code="GATEWAY_ERROR",
        failure_class="TRANSIENT_GATEWAY",
        confidence=0.75, # < 0.85 high-value confidence threshold
        recommended_strategy="DELAYED_RETRY",
        diagnostic_summary="Uncertain high value"
    )
    verdict = PolicyEngine.evaluate(diagnosis=diag, attempt_count=1)
    assert verdict.passed_all_gates is False
    assert verdict.verdict == "ESCALATED_HUMAN"

def test_attack_08_quiet_hours_outreach_block():
    diag = DiagnosisProposal(
        payment_id="pay_qh_01",
        amount=1500.0,
        raw_error_code="INSUFFICIENT_FUNDS",
        failure_class="INSUFFICIENT_FUNDS",
        confidence=0.90,
        recommended_strategy="DISPATCH_PAYMENT_LINK",
        diagnostic_summary="Late night drop"
    )
    # 22:30 IST is 17:00 UTC
    epoch_night_utc = 1724691600.0
    verdict = PolicyEngine.evaluate(diagnosis=diag, attempt_count=1, channel="WHATSAPP", current_epoch=epoch_night_utc)
    assert verdict.verdict == "DEFERRED_QUIET_HOURS"
    assert verdict.scheduled_epoch is not None

def test_attack_09_fourth_retry_attempt_breach():
    diag = DiagnosisProposal(
        payment_id="pay_retry_04",
        amount=500.0,
        raw_error_code="GATEWAY_ERROR",
        failure_class="TRANSIENT_GATEWAY",
        confidence=0.90,
        recommended_strategy="DELAYED_RETRY",
        diagnostic_summary="Attempt 4"
    )
    verdict = PolicyEngine.evaluate(diagnosis=diag, attempt_count=4)
    assert verdict.verdict == "SUPPRESSED"
    assert "MAX_RETRIES_EXCEEDED" in verdict.violated_rules[0]

def test_attack_10_excessive_discount_clamping():
    # 50% discount on INR 10,000 = INR 5,000 -> Clamped strictly to INR 500
    clamped = PolicyEngine.clamp_recovery_discount(transaction_amount=10000.0, proposed_discount_pct=50.0)
    assert clamped == 500.0

def test_attack_11_illegal_fsm_jump():
    fsm = B2BReceivablesStateMachine()
    with pytest.raises(ValueError):
        fsm.transition("inv_999", "CLOSED", "ATTEMPTED_DIRECT_CLOSE")

def test_attack_12_commercial_dispute_human_escalation():
    engine = B2BVoiceDialogueEngine()
    req = VoiceDialogueTurnRequest(
        invoice_id="inv_dispute_01",
        customer_speech_text="Ye product kharaab tha, hum payment nahi denge aur lawyer se baat karenge.",
        invoice_amount=50000.0
    )
    resp = engine.process_customer_turn(req)
    assert resp.action_taken == "ESCALATE_TO_HUMAN_CFO"
    assert resp.should_escalate_to_human is True
    assert resp.fsm_current_state == "ESCALATED"
