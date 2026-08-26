import time
import logging
from typing import Dict, Any, List, Optional, Set
from backend.app.schemas import B2BStateTransition

logger = logging.getLogger("RazorRevive.B2B.StateMachine")

class B2BReceivablesStateMachine:
    """
    Finite State Machine for High-Value B2B Accounts Receivable.
    Strictly validates every state transition to prevent arbitrary state jumps or unverified mutations.
    """

    STATES: Set[str] = {
        "OVERDUE",
        "CONTACT_PENDING",
        "CONTACTED",
        "DISPUTE_DETECTED",
        "DISPUTE_REVIEW",
        "RESOLUTION_PROPOSED",
        "PTP_REGISTERED",
        "PAYMENT_PENDING",
        "RECOVERED",
        "ESCALATED",
        "SUPPRESSED",
        "FAILED",
        "CLOSED"
    }

    # Strict transition table (from_state -> set of allowed to_states)
    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        "OVERDUE": {"CONTACT_PENDING", "ESCALATED", "SUPPRESSED"},
        "CONTACT_PENDING": {"CONTACTED", "FAILED", "ESCALATED"},
        "CONTACTED": {"DISPUTE_DETECTED", "PTP_REGISTERED", "RECOVERED", "ESCALATED"},
        "DISPUTE_DETECTED": {"DISPUTE_REVIEW", "ESCALATED"},
        "DISPUTE_REVIEW": {"RESOLUTION_PROPOSED", "ESCALATED", "FAILED"},
        "RESOLUTION_PROPOSED": {"PTP_REGISTERED", "PAYMENT_PENDING", "RECOVERED", "ESCALATED"},
        "PTP_REGISTERED": {"PAYMENT_PENDING", "RECOVERED", "ESCALATED", "FAILED"},
        "PAYMENT_PENDING": {"RECOVERED", "FAILED", "ESCALATED"},
        "RECOVERED": {"CLOSED"},
        "ESCALATED": {"CLOSED", "DISPUTE_REVIEW", "PTP_REGISTERED"},
        "FAILED": {"CONTACT_PENDING", "ESCALATED", "CLOSED"},
        "SUPPRESSED": {"CLOSED"},
        "CLOSED": set()
    }

    def __init__(self):
        self._active_states: Dict[str, str] = {}
        self._transition_history: Dict[str, List[B2BStateTransition]] = {}

    def get_state(self, invoice_id: str) -> str:
        return self._active_states.get(invoice_id, "OVERDUE")

    def transition(
        self,
        invoice_id: str,
        to_state: str,
        trigger_event: str,
        actor: str = "SYSTEM_AUTOMATION",
        metadata: Optional[Dict[str, Any]] = None
    ) -> B2BStateTransition:
        """
        Executes a validated state transition. Raises ValueError on invalid transition.
        """
        current_state = self.get_state(invoice_id)

        if to_state not in self.STATES:
            raise ValueError(f"Unknown target state: {to_state}")

        allowed_targets = self.VALID_TRANSITIONS.get(current_state, set())
        if to_state not in allowed_targets:
            err_msg = f"Invalid state transition for invoice {invoice_id}: {current_state} -> {to_state}. Allowed: {allowed_targets}"
            logger.error(f"[B2B_FSM_VIOLATION] {err_msg}")
            raise ValueError(err_msg)

        transition_record = B2BStateTransition(
            invoice_id=invoice_id,
            from_state=current_state,
            to_state=to_state,
            trigger_event=trigger_event,
            actor=actor,
            timestamp=time.time(),
            metadata=metadata or {}
        )

        self._active_states[invoice_id] = to_state
        if invoice_id not in self._transition_history:
            self._transition_history[invoice_id] = []
        self._transition_history[invoice_id].append(transition_record)

        logger.info(f"[B2B_FSM] Invoice {invoice_id}: {current_state} -> {to_state} via {trigger_event}")
        return transition_record

    def get_history(self, invoice_id: str) -> List[B2BStateTransition]:
        return self._transition_history.get(invoice_id, [])

b2b_fsm = B2BReceivablesStateMachine()
