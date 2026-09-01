import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_contract_healthcheck():
    response = client.get("/health")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    assert "data" in json_data
    assert "trace_id" in json_data

def test_contract_simulated_failure_valid():
    payload = {
        "payment_id": "pay_test_contract_01",
        "amount": 2499.0,
        "error_code": "GATEWAY_ERROR",
        "error_description": "Bank timeout",
        "customer_phone": "+919876543210",
        "customer_email": "user@example.com"
    }
    response = client.post("/api/v1/simulate/failure", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["payment_id"] == "pay_test_contract_01"
    assert "decision_trace" in data["data"]
    assert "trace_id" in data

def test_contract_b2b_voice_turn_valid():
    payload = {
        "call_session_id": "call_123",
        "invoice_id": "inv_998",
        "customer_speech_text": "Sir invoice mein hamara GST number galat hai, correct GSTIN 29AABCU9603R1Z2 daal kar bhejiye.",
        "invoice_amount": 85000.0
    }
    response = client.post("/api/v1/b2b/voice/turn", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["action_taken"] == "MUTATE_RAZORPAY_INVOICE"
    assert "trace_id" in data

def test_contract_audit_verify_endpoint():
    response = client.get("/api/v1/audit/verify")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "valid" in data["data"]
    assert data["data"]["tampering_detected"] is False

def test_contract_http_422_validation_error():
    # Negative amount violates schema gt=0.0
    payload = {
        "payment_id": "pay_invalid",
        "amount": -100.0
    }
    response = client.post("/api/v1/simulate/failure", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "SCHEMA_VALIDATION_ERROR"
    assert "trace_id" in data

def test_contract_security_headers_present():
    response = client.get("/health")
    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-Trace-ID") is not None

def test_contract_prometheus_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "razorrevive_recovery_requests_total" in response.text
    assert "razorrevive_diagnostic_latency_seconds" in response.text

def test_contract_roi_calculator():
    response = client.get("/api/v1/analytics/roi?monthly_gmv=10000000&failure_rate_pct=15.0")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["monthly_gmv_inr"] == 10000000.0
    assert data["data"]["failed_gmv_inr"] == 1500000.0
    assert data["data"]["projected_monthly_recovered_gmv_inr"] > 600000.0
    assert "retained_customers_monthly" in data["data"]

def test_contract_upi_qr_generation():
    payload = {
        "payment_id": "pay_test_upi_88",
        "amount": 3499.0,
        "merchant_vpa": "razorpay.test@icici",
        "merchant_name": "Test Merchant"
    }
    response = client.post("/api/v1/recovery/upi-qr", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "upi://" in data["data"]["upi_uri"]
    assert "gpay" in data["data"]["app_intents"]
    assert "<svg" in data["data"]["svg_qr"]


