import pytest
import time
from backend.app.b2b.state_machine import B2BReceivablesStateMachine
from backend.app.b2b.voice_agent import b2b_voice_engine, VoiceDialogueTurnRequest

def test_b2b_fsm_persistence_across_reboots():
    inv_id = f"inv_durability_{int(time.time())}"
    
    # 1. Instance A transitions state
    fsm_instance_a = B2BReceivablesStateMachine()
    fsm_instance_a.transition(inv_id, "CONTACT_PENDING", "INITIAL_VOICE_DUNNING")
    fsm_instance_a.transition(inv_id, "CONTACTED", "CUSTOMER_ANSWERED")
    fsm_instance_a.transition(inv_id, "DISPUTE_DETECTED", "GST_DISPUTE_FLAGGED")
    
    assert fsm_instance_a.get_state(inv_id) == "DISPUTE_DETECTED"
    
    # 2. Simulate Server Reboot: create new fresh Instance B pointing to same SQLite WAL DB
    fsm_instance_b = B2BReceivablesStateMachine()
    
    # Verify hydrated state is preserved
    assert fsm_instance_b.get_state(inv_id) == "DISPUTE_DETECTED"
    
    # Verify transition history is fully restored
    history = fsm_instance_b.get_history(inv_id)
    assert len(history) == 3
    assert history[-1].to_state == "DISPUTE_DETECTED"
    
    # Continue lifecycle on Instance B
    fsm_instance_b.transition(inv_id, "DISPUTE_REVIEW", "CFO_REVIEWING_GST")
    assert fsm_instance_b.get_state(inv_id) == "DISPUTE_REVIEW"

def test_b2b_voice_utr_extraction():
    req = VoiceDialogueTurnRequest(
        call_session_id="call_utr_01",
        invoice_id="inv_utr_test_99",
        customer_speech_text="Haan sir maine UTR AXISN88990011 se payment already transfer kar diya hai",
        customer_phone="+919876543210",
        invoice_amount=50000.0
    )
    res = b2b_voice_engine.process_customer_turn(req)
    assert res.intent_detected == "UTR_SETTLEMENT_CONFIRMATION"
    assert res.action_taken == "RECORD_SETTLEMENT_REFERENCE"
    assert res.fsm_current_state == "PAYMENT_PENDING"

def test_b2b_voice_tds_deduction():
    req = VoiceDialogueTurnRequest(
        call_session_id="call_tds_01",
        invoice_id="inv_tds_test_88",
        customer_speech_text="Sir hamari company 10% TDS deduct karke baaki payment release karegi",
        customer_phone="+919876543210",
        invoice_amount=100000.0
    )
    res = b2b_voice_engine.process_customer_turn(req)
    assert res.intent_detected == "TDS_DEDUCTION_DISPUTE"
    assert res.action_taken == "MUTATE_INVOICE_TDS_ADJUSTMENT"
    assert res.invoice_mutated is True
    assert res.mutation_proposal is not None
    assert res.mutation_proposal.dispute_category == "TDS_STATUTORY_DEDUCTION"
    assert res.mutation_proposal.new_value == "90000.0" # 100,000 - 10,000 TDS
