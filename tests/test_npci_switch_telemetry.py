import pytest
from backend.app.telemetry_npci import npci_telemetry
from backend.app.recovery_optimizer import recovery_optimizer
from backend.app.diagnostic_engine import diagnostic_engine

def test_npci_switch_initial_states():
    switches = npci_telemetry.get_all_switches()
    assert len(switches) >= 6
    bank_codes = [s.bank_code for s in switches]
    assert "HDFC" in bank_codes
    assert "SBI" in bank_codes
    assert "PNB" in bank_codes

def test_npci_switch_circuit_breaker_and_degradation():
    # PNB is in outage state -> circuit breaker should be tripped
    pnb_status = npci_telemetry.get_switch_status("PNB")
    assert pnb_status.switch_state == "OUTAGE"
    assert pnb_status.circuit_breaker_tripped is True
    assert pnb_status.recommended_fallback_rail == "REROUTE_TO_ALTERNATE_BANK_VPA"

def test_npci_switch_dynamic_hazard_window():
    # Healthy bank (ICICI) vs Degraded bank (SBI) vs Outage bank (PNB)
    rec_icici = recovery_optimizer.select_optimal_retry_window(
        failure_class="TRANSIENT_GATEWAY",
        attempt_number=1,
        bank_issuer="ICICI"
    )
    rec_sbi = recovery_optimizer.select_optimal_retry_window(
        failure_class="TRANSIENT_GATEWAY",
        attempt_number=1,
        bank_issuer="SBI"
    )
    rec_pnb = recovery_optimizer.select_optimal_retry_window(
        failure_class="TRANSIENT_GATEWAY",
        attempt_number=1,
        bank_issuer="PNB"
    )
    
    assert rec_icici.recommended_retry_delay_minutes <= 45
    assert rec_sbi.recommended_retry_delay_minutes >= 45
    assert rec_pnb.recommended_retry_delay_minutes >= 90
    assert "NPCI Switch Status" in rec_pnb.reason

def test_npci_switch_telemetry_live_update():
    updated = npci_telemetry.update_switch_telemetry(
        bank_code="HDFC",
        state="DEGRADED",
        success_rate_pct=65.0,
        latency_ms=1200.0,
        incidents=["HDFC Core UPI switch maintenance window active"]
    )
    assert updated.switch_state == "DEGRADED"
    assert updated.success_rate_pct == 65.0
    
    # Verify optimizer reacts to updated telemetry
    rec = recovery_optimizer.select_optimal_retry_window(
        failure_class="TRANSIENT_GATEWAY",
        attempt_number=1,
        bank_issuer="HDFC"
    )
    assert rec.recommended_retry_delay_minutes >= 45
    assert "DEGRADED" in rec.reason

    # Restore HDFC to healthy
    npci_telemetry.update_switch_telemetry(
        bank_code="HDFC",
        state="HEALTHY",
        success_rate_pct=95.0,
        latency_ms=300.0
    )

def test_npci_error_code_classification():
    diag = diagnostic_engine.diagnose(
        payment_id="pay_npci_991",
        amount=5000.0,
        error_code="UPI_U30_DEGRADATION"
    )
    assert diag.failure_class == "TRANSIENT_GATEWAY"
    assert diag.recommended_strategy == "DELAYED_RETRY"
    assert "NPCI_UPI_U30_CORE_SWITCH_DEGRADATION" in diag.reason_codes
