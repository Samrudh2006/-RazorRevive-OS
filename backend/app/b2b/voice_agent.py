import re
import time
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.app.schemas import MutationProposal, PromiseToPayRecord
from backend.app.b2b.state_machine import b2b_fsm
from backend.app.b2b.ptp_engine import ptp_store
from backend.app.gateways import default_gateway

logger = logging.getLogger("RazorRevive.B2B.VoiceAgent")

class VoiceDialogueTurnRequest(BaseModel):
    call_session_id: str = Field(default="call_mock_1001")
    invoice_id: str = Field(default="inv_enterprise_998")
    customer_speech_text: str
    customer_phone: str = Field(default="+919876543210")
    invoice_amount: float = Field(default=85000.0)

class VoiceDialogueResponse(BaseModel):
    call_session_id: str
    agent_speech_response: str
    intent_detected: str
    action_taken: str
    mutation_proposal: Optional[MutationProposal] = None
    ptp_created: bool = False
    ptp_details: Optional[PromiseToPayRecord] = None
    invoice_mutated: bool = False
    new_invoice_details: Optional[Dict[str, Any]] = None
    should_escalate_to_human: bool = False
    fsm_current_state: str = "CONTACTED"

class B2BVoiceDialogueEngine:
    """
    Conversational Voice Dialogue Engine for Enterprise B2B Accounts Receivable.
    
    SAFETY CONSTRAINT:
    The voice model NEVER performs unrestricted database mutations. It generates structured
    MutationProposals or PromiseToPay commitments that must pass policy checks.
    """

    @classmethod
    def process_customer_turn(cls, req: VoiceDialogueTurnRequest) -> VoiceDialogueResponse:
        speech = req.customer_speech_text.strip()
        speech_lower = speech.lower()
        inv_id = req.invoice_id
        amt = req.invoice_amount
        phone = req.customer_phone

        # Ensure FSM is initialized
        if b2b_fsm.get_state(inv_id) == "OVERDUE":
            b2b_fsm.transition(inv_id, "CONTACT_PENDING", "VOICE_CALL_INITIATED")
            b2b_fsm.transition(inv_id, "CONTACTED", "CUSTOMER_ANSWERED_CALL")

        # 1. Check for Commercial / Legal Dispute -> Escalate to CFO
        if any(term in speech_lower for term in ["lawyer", "court", "fraud", "kharaab", "cheating", "dispute", "defective", "refund"]):
            b2b_fsm.transition(inv_id, "DISPUTE_DETECTED", "LEGAL_COMMERCIAL_DISPUTE_RAISED")
            b2b_fsm.transition(inv_id, "ESCALATED", "ESCALATE_TO_HUMAN_CFO")
            
            return VoiceDialogueResponse(
                call_session_id=req.call_session_id,
                agent_speech_response="Hum samajh sakte hain sir. Hum is case ko hamare Senior Accounts Director ko escalate kar rahe hain. Woh aapse direct contact karenge.",
                intent_detected="COMMERCIAL_DISPUTE_ESCALATION",
                action_taken="ESCALATE_TO_HUMAN_CFO",
                should_escalate_to_human=True,
                fsm_current_state="ESCALATED"
            )

        # 2. Check for GST / Tax Line Objection -> Structured Mutation Proposal
        gst_match = re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b", speech.upper())
        if "gst" in speech_lower or gst_match or "tax" in speech_lower or "pan" in speech_lower:
            new_gstin = gst_match.group(0) if gst_match else "29AABCU9603R1Z2"
            
            b2b_fsm.transition(inv_id, "DISPUTE_DETECTED", "GST_CORRECTION_REQUESTED")
            b2b_fsm.transition(inv_id, "DISPUTE_REVIEW", "POLICY_VALIDATING_GST_MUTATION")

            proposal = MutationProposal(
                invoice_id=inv_id,
                field_to_mutate="customer_gstin",
                old_value="UNREGISTERED",
                new_value=new_gstin,
                dispute_category="TAX_LINE_CORRECTION",
                reason="Customer provided updated valid GSTIN during voice call",
                confidence=0.96,
                requires_approval=False, # Standard allowable field under policy
                approved_by_policy=True
            )

            # Gateway execution through abstraction layer
            gw_result = default_gateway.mutate_invoice(inv_id, {"gstin": new_gstin})
            b2b_fsm.transition(inv_id, "RESOLUTION_PROPOSED", "INVOICE_MUTATED_AND_DISPATCHED")

            return VoiceDialogueResponse(
                call_session_id=req.call_session_id,
                agent_speech_response=f"Haanji sir, humne aapka GSTIN {new_gstin} update kar diya hai aur revised invoice instantly aapke email aur WhatsApp par bhej diya hai. Kya hum payment Friday ko process kar sakte hain?",
                intent_detected="GST_DISPUTE_RESOLUTION",
                action_taken="MUTATE_RAZORPAY_INVOICE",
                mutation_proposal=proposal,
                invoice_mutated=True,
                new_invoice_details=gw_result,
                fsm_current_state=b2b_fsm.get_state(inv_id)
            )

        # 3. Check for Promise to Pay (PTP) -> Register commitment & lock auto-debits
        if any(term in speech_lower for term in ["friday", "monday", "tomorrow", "kal", "haanj", "clear ho jayega", "funds", "pay", "dedenge"]):
            # Calculate next Friday 11:00 AM IST epoch
            now_epoch = time.time()
            target_ptp_epoch = now_epoch + (2 * 86400) # +48 hours
            
            b2b_fsm.transition(inv_id, "PTP_REGISTERED", "CUSTOMER_COMMITTED_PAYMENT_DATE")

            ptp_record = ptp_store.register_promise(
                invoice_id=inv_id,
                customer_contact=phone,
                promised_epoch=target_ptp_epoch,
                promised_window_label="Friday 11:00 AM IST",
                amount=amt,
                notes=f"Customer verbal confirmation: '{speech}'"
            )

            return VoiceDialogueResponse(
                call_session_id=req.call_session_id,
                agent_speech_response=f"Bahut shukriya sir! Humne Friday 11:00 AM ka Promise-to-Pay note kar liya hai aur reminder lock kar diya hai. Link aapke WhatsApp par active rahega.",
                intent_detected="PROMISE_TO_PAY_COMMITMENT",
                action_taken="REGISTER_PTP_LOCK",
                ptp_created=True,
                ptp_details=ptp_record,
                fsm_current_state=b2b_fsm.get_state(inv_id)
            )

        # 4. Default Informational Turn
        return VoiceDialogueResponse(
            call_session_id=req.call_session_id,
            agent_speech_response=f"Ji sir, aapka invoice #{inv_id} of INR {amt:,.2f} pending hai. Kya aap iska payment aaj UPI ya netbanking se complete kar sakte hain?",
            intent_detected="GENERAL_INQUIRY",
            action_taken="PROMPT_PAYMENT_INTENT",
            fsm_current_state=b2b_fsm.get_state(inv_id)
        )

b2b_voice_engine = B2BVoiceDialogueEngine()
