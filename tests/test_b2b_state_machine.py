import pytest
from backend.app.b2b.state_machine import B2BReceivablesStateMachine
from backend.app.b2b.voice_agent import B2BVoiceDialogueEngine, VoiceDialogueTurnRequest
from backend.app.b2b.ptp_engine import PTPStore

def test_fsm_valid_transition_lifecycle():
    fsm = B2BReceivablesStateMachine()
    inv_id = "inv_fsm_test_01"
    fsm.reset_state(inv_id)

    # OVERDUE -> CONTACT_PENDING
    t1 = fsm.transition(inv_id, "CONTACT_PENDING", "TRIGGER_CALL")
    assert t1.to_state == "CONTACT_PENDING"

    # CONTACT_PENDING -> CONTACTED
    t2 = fsm.transition(inv_id, "CONTACTED", "ANSWER_CALL")
    assert t2.to_state == "CONTACTED"

    # CONTACTED -> DISPUTE_DETECTED
    t3 = fsm.transition(inv_id, "DISPUTE_DETECTED", "OBJECTION_RAISED")
    assert t3.to_state == "DISPUTE_DETECTED"

    # DISPUTE_DETECTED -> DISPUTE_REVIEW
    t4 = fsm.transition(inv_id, "DISPUTE_REVIEW", "POLICY_REVIEW")
    assert t4.to_state == "DISPUTE_REVIEW"

    # DISPUTE_REVIEW -> RESOLUTION_PROPOSED
    t5 = fsm.transition(inv_id, "RESOLUTION_PROPOSED", "PROPOSE_MUTATION")
    assert t5.to_state == "RESOLUTION_PROPOSED"

    # RESOLUTION_PROPOSED -> PTP_REGISTERED
    t6 = fsm.transition(inv_id, "PTP_REGISTERED", "PROMISE_DATE")
    assert t6.to_state == "PTP_REGISTERED"

    # PTP_REGISTERED -> RECOVERED
    t7 = fsm.transition(inv_id, "RECOVERED", "PAYMENT_SETTLED")
    assert t7.to_state == "RECOVERED"

    # RECOVERED -> CLOSED
    t8 = fsm.transition(inv_id, "CLOSED", "LEDGER_SETTLED")
    assert t8.to_state == "CLOSED"

def test_fsm_invalid_transition_rejection():
    fsm = B2BReceivablesStateMachine()
    inv_id = "inv_fsm_invalid_01"

    # Cannot jump directly from OVERDUE to RECOVERED without intermediate lifecycle
    with pytest.raises(ValueError) as excinfo:
        fsm.transition(inv_id, "RECOVERED", "ILLEGAL_JUMP")
    assert "Invalid state transition" in str(excinfo.value)

def test_voice_agent_gst_mutation_proposal():
    engine = B2BVoiceDialogueEngine()
    req = VoiceDialogueTurnRequest(
        call_session_id="call_999",
        invoice_id="inv_gst_01",
        customer_speech_text="Sir invoice mein hamara GST number galat hai, correct GSTIN 29AABCU9603R1Z2 daal kar bhejiye.",
        invoice_amount=85000.0
    )
    
    resp = engine.process_customer_turn(req)
    assert resp.intent_detected == "GST_DISPUTE_RESOLUTION"
    assert resp.action_taken == "MUTATE_RAZORPAY_INVOICE"
    assert resp.invoice_mutated is True
    assert resp.mutation_proposal is not None
    assert resp.mutation_proposal.new_value == "29AABCU9603R1Z2"
    assert resp.mutation_proposal.approved_by_policy is True

def test_voice_agent_promise_to_pay_registration():
    engine = B2BVoiceDialogueEngine()
    req = VoiceDialogueTurnRequest(
        call_session_id="call_998",
        invoice_id="inv_ptp_01",
        customer_speech_text="Haanji sir, accountant Friday ko aayega aur funds clear ho jayega 11 baje.",
        invoice_amount=85000.0
    )

    resp = engine.process_customer_turn(req)
    assert resp.intent_detected == "PROMISE_TO_PAY_COMMITMENT"
    assert resp.action_taken == "REGISTER_PTP_LOCK"
    assert resp.ptp_created is True
    assert resp.ptp_details is not None
    assert resp.ptp_details.promised_window_label == "Friday 11:00 AM IST"
