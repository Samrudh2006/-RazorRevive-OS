import pytest
from backend.app.token_lifecycle import card_token_manager
from backend.app.diagnostic_engine import diagnostic_engine

def test_card_token_revocation_remediation():
    record = card_token_manager.inspect_token_error(
        token_id="tok_visa_vts_101",
        error_code="TOKEN_REVOKED",
        card_network="VISA_VTS",
        last_four="8899"
    )
    assert record.token_status == "REVOKED"
    assert record.remediation_action == "AUTOMATIC_TOKEN_REPROVISION"
    assert record.retry_allowed_on_token is False
    assert record.card_network == "VISA_VTS"

def test_card_token_cryptogram_invalid():
    record = card_token_manager.inspect_token_error(
        token_id="tok_mdes_202",
        error_code="CARD_TOKEN_CRYPTOGRAM_INVALID",
        card_network="MASTERCARD_MDES",
        last_four="4455"
    )
    assert record.token_status == "CRYPTOGRAM_EXPIRED"
    assert record.remediation_action == "AUTOMATIC_TOKEN_REPROVISION"

def test_card_token_suspended():
    record = card_token_manager.inspect_token_error(
        token_id="tok_rupay_303",
        error_code="TOKEN_SUSPENDED",
        card_network="RUPAY_TOKEN",
        last_four="1122"
    )
    assert record.token_status == "SUSPENDED"
    assert record.remediation_action == "STEP_UP_2FA_CONSENT"
    assert record.retry_allowed_on_token is True

def test_card_token_diagnostic_classification():
    diag = diagnostic_engine.diagnose(
        payment_id="pay_tok_test_01",
        amount=3499.0,
        error_code="TOKEN_REVOKED"
    )
    assert diag.failure_class == "EXPIRED_MANDATE"
    assert diag.recommended_strategy == "DISPATCH_PAYMENT_LINK"
    assert "NETWORK_TOKEN_REPROVISION_REQUIRED" in diag.reason_codes
