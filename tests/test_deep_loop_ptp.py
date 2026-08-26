import pytest
from backend.app.b2b.voice_agent import B2BVoiceDialogueEngine, VoiceDialogueTurnRequest
from backend.app.b2b.ptp_engine import PTPStore

def test_b2b_voice_gst_dispute_mutation():
    engine = B2BVoiceDialogueEngine()
    req = VoiceDialogueTurnRequest(
        call_session_id="call_mock_1",
        invoice_id="inv_enterprise_998",
        customer_speech_text="Sir invoice mein hamara GST number galat hai, correct GSTIN 29AABCU9603R1Z2 daal kar bhejiye.",
        invoice_amount=85000.0
    )
    resp = engine.process_customer_turn(req)
    
    assert resp.intent_detected == "GST_DISPUTE_RESOLUTION"
    assert resp.action_taken == "MUTATE_RAZORPAY_INVOICE"
    assert resp.invoice_mutated is True
    assert resp.mutation_proposal is not None
    assert resp.mutation_proposal.new_value == "29AABCU9603R1Z2"

def test_b2b_voice_promise_to_pay_registration(tmp_path):
    engine = B2BVoiceDialogueEngine()
    req = VoiceDialogueTurnRequest(
        call_session_id="call_mock_2",
        invoice_id="inv_enterprise_777",
        customer_speech_text="Haanji sir, accountant Friday ko aayega aur funds clear ho jayega 11 baje.",
        invoice_amount=85000.0
    )
    resp = engine.process_customer_turn(req)
    
    assert resp.intent_detected == "PROMISE_TO_PAY_COMMITMENT"
    assert resp.action_taken == "REGISTER_PTP_LOCK"
    assert resp.ptp_created is True
    assert resp.ptp_details is not None

def test_b2b_voice_dispute_human_escalation():
    engine = B2BVoiceDialogueEngine()
    req = VoiceDialogueTurnRequest(
        call_session_id="call_mock_3",
        invoice_id="inv_enterprise_666",
        customer_speech_text="Ye product bilkul kharaab tha, hum payment nahi denge aur lawyer se baat karenge.",
        invoice_amount=85000.0
    )
    resp = engine.process_customer_turn(req)
    
    assert resp.intent_detected == "COMMERCIAL_DISPUTE_ESCALATION"
    assert resp.action_taken == "ESCALATE_TO_HUMAN_CFO"
    assert resp.should_escalate_to_human is True
    assert resp.fsm_current_state == "ESCALATED"
