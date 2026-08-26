import time
import pytest
from backend.app.schemas import DiagnosisProposal
from backend.app.policy_engine import PolicyEngine

def test_trai_quiet_hours_detection():
    # 22:30 IST is 17:00 UTC
    epoch_night_utc = 1724691600.0
    assert PolicyEngine.is_trai_quiet_hours(epoch_night_utc) is True

    # 14:30 IST is 09:00 UTC
    epoch_day_utc = 1724662800.0
    assert PolicyEngine.is_trai_quiet_hours(epoch_day_utc) is False

def test_discount_boundary_clamping():
    # 20% discount on INR 10,000 = INR 2,000 -> must clamp to MAX_DISCOUNT_AMOUNT_INR (INR 500)
    clamped1 = PolicyEngine.clamp_recovery_discount(transaction_amount=10000.0, proposed_discount_pct=20.0)
    assert clamped1 == 500.0

    # 5% discount on INR 1,000 = INR 50 -> allowed (below INR 500 and <= 10%)
    clamped2 = PolicyEngine.clamp_recovery_discount(transaction_amount=1000.0, proposed_discount_pct=5.0)
    assert clamped2 == 50.0

def test_high_value_transaction_escalation():
    diag = DiagnosisProposal(
        payment_id="pay_high_val_01",
        amount=75000.0,
        raw_error_code="GATEWAY_ERROR",
        failure_class="TRANSIENT_GATEWAY",
        confidence=0.75,
        recommended_strategy="DELAYED_RETRY",
        diagnostic_summary="Uncertain bank recovery on high value invoice"
    )
    
    result = PolicyEngine.evaluate(diagnosis=diag, attempt_count=1)
    assert result.passed_all_gates is False
    assert result.verdict == "ESCALATED_HUMAN"

def test_max_retry_attempt_suppression():
    diag = DiagnosisProposal(
        payment_id="pay_retry_overflow",
        amount=999.0,
        raw_error_code="INSUFFICIENT_FUNDS",
        failure_class="INSUFFICIENT_FUNDS",
        confidence=0.90,
        recommended_strategy="DISPATCH_PAYMENT_LINK",
        diagnostic_summary="Third failed retry"
    )
    
    result = PolicyEngine.evaluate(diagnosis=diag, attempt_count=4)
    assert result.passed_all_gates is False
    assert result.verdict == "SUPPRESSED"

def test_low_confidence_suppression():
    diag = DiagnosisProposal(
        payment_id="pay_low_conf_01",
        amount=1200.0,
        raw_error_code="UNKNOWN_ANOMALY",
        failure_class="TRANSIENT_GATEWAY",
        confidence=0.45,
        recommended_strategy="DISPATCH_PAYMENT_LINK",
        diagnostic_summary="Very low diagnostic signal"
    )
    
    result = PolicyEngine.evaluate(diagnosis=diag, attempt_count=1)
    assert result.passed_all_gates is False
    assert result.verdict == "SUPPRESSED"
