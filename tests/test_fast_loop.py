import pytest
from backend.app.diagnostic_engine import DiagnosticEngine
from backend.app.recovery_optimizer import RecoveryHazardOptimizer
from backend.app.gateways.razorpay_adapter import RazorpayTestAdapter

def test_diagnostic_engine_classifications():
    # 1. Gateway Error Classification
    d1 = DiagnosticEngine.diagnose(
        payment_id="pay_diag_01",
        amount=2499.0,
        error_code="GATEWAY_ERROR",
        error_description="Bank gateway timeout"
    )
    assert d1.failure_class == "TRANSIENT_GATEWAY"
    assert d1.recommended_strategy == "DELAYED_RETRY"
    assert d1.confidence >= 0.90

    # 2. Insufficient Funds Classification
    d2 = DiagnosticEngine.diagnose(
        payment_id="pay_diag_02",
        amount=999.0,
        error_code="INSUFFICIENT_FUNDS",
        error_description="Low balance"
    )
    assert d2.failure_class == "INSUFFICIENT_FUNDS"
    assert d2.recommended_strategy == "DISPATCH_PAYMENT_LINK"

    # 3. Suspicious Velocity Anomaly
    d3 = DiagnosticEngine.diagnose(
        payment_id="pay_diag_03",
        amount=85000.0,
        error_code="SUSPICIOUS_VELOCITY",
        error_description="Card testing pattern"
    )
    assert d3.failure_class == "SUSPICIOUS_VELOCITY"
    assert d3.recommended_strategy == "ESCALATE_HUMAN"
    assert d3.requires_human is True

def test_recovery_hazard_calculations():
    # Test hazard peak selection for HDFC node
    rec = RecoveryHazardOptimizer.select_optimal_retry_window(
        failure_class="TRANSIENT_GATEWAY",
        attempt_number=1,
        bank_issuer="HDFC"
    )
    assert rec.recommended_retry_delay_minutes in [30, 45, 60]
    assert rec.success_probability > 0.70
    assert rec.model_version == "recovery-hazard-v1"

def test_gateway_adapter_payment_link():
    adapter = RazorpayTestAdapter()
    res = adapter.create_recovery_link(
        payment_id="pay_unit_test",
        amount=2499.0,
        customer_name="Test Customer",
        customer_email="test@example.com",
        customer_phone="+919876543210",
        discount_amount=100.0
    )
    assert res["success"] is True
    assert res["final_amount"] == 2399.0
    assert "short_url" in res
    assert "https://" in res["short_url"]

def test_llm_prompt_builder():
    prompt = DiagnosticEngine.build_llm_prompt(
        payment_id="pay_prompt_01",
        amount=5000.0,
        error_code="GATEWAY_ERROR",
        error_description="HDFC node timeout"
    )
    assert "system" in prompt
    assert "user" in prompt
    assert "TRANSIENT_GATEWAY" in prompt["system"]
    assert "pay_prompt_01" in prompt["user"]

def test_local_vector_space_semantic_classifier():
    from backend.app.diagnostic_engine import LocalVectorSpaceSemanticClassifier
    
    # 1. Test bank timeout classification
    f_class, conf = LocalVectorSpaceSemanticClassifier.classify("Bank gateway server degraded 504 timeout")
    assert f_class == "TRANSIENT_GATEWAY"
    assert conf >= 0.70
    
    # 2. Test balance decline classification
    f_class2, conf2 = LocalVectorSpaceSemanticClassifier.classify("Customer account balance insufficient for transfer")
    assert f_class2 == "INSUFFICIENT_FUNDS"
    assert conf2 >= 0.70

    # 3. Test fraud risk classification
    f_class3, conf3 = LocalVectorSpaceSemanticClassifier.classify("High risk velocity anomaly detected card testing")
    assert f_class3 == "SUSPICIOUS_VELOCITY"
    assert conf3 >= 0.70

def test_local_ollama_client_offline_fallback():
    from backend.app.diagnostic_engine import LocalOllamaClient
    
    # Verify that querying an offline port gracefully returns None without raising exceptions
    prompt = {"system": "System Prompt", "user": "User Prompt"}
    res = LocalOllamaClient.query_local_llm(
        prompt=prompt,
        base_url="http://127.0.0.1:59999", # Non-existent port
        timeout_sec=0.1
    )
    assert res is None


