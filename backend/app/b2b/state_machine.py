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
        "OVERDUE": {"CONTACT_PENDING", "ESCALATED", "SUPPRESSED", "CONTACTED"},
        "CONTACT_PENDING": {"CONTACTED", "FAILED", "ESCALATED", "DISPUTE_DETECTED"},
        "CONTACTED": {"DISPUTE_DETECTED", "PTP_REGISTERED", "RECOVERED", "ESCALATED", "PAYMENT_PENDING"},
        "DISPUTE_DETECTED": {"DISPUTE_REVIEW", "ESCALATED", "RESOLUTION_PROPOSED"},
        "DISPUTE_REVIEW": {"RESOLUTION_PROPOSED", "ESCALATED", "FAILED", "DISPUTE_DETECTED"},
        "RESOLUTION_PROPOSED": {"PTP_REGISTERED", "PAYMENT_PENDING", "RECOVERED", "ESCALATED", "DISPUTE_DETECTED", "DISPUTE_REVIEW", "CONTACTED"},
        "PTP_REGISTERED": {"PAYMENT_PENDING", "RECOVERED", "ESCALATED", "FAILED", "DISPUTE_DETECTED"},
        "PAYMENT_PENDING": {"RECOVERED", "FAILED", "ESCALATED", "PTP_REGISTERED"},
        "RECOVERED": {"CLOSED"},
        "ESCALATED": {"CLOSED", "DISPUTE_REVIEW", "PTP_REGISTERED", "CONTACTED"},
        "FAILED": {"CONTACT_PENDING", "ESCALATED", "CLOSED"},
        "SUPPRESSED": {"CLOSED"},
        "CLOSED": set()
    }

    def reset_state(self, invoice_id: str, state: str = "OVERDUE"):
        self._active_states[invoice_id] = state
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM b2b_fsm_states WHERE invoice_id = ?", (invoice_id,))
                conn.execute("DELETE FROM b2b_fsm_history WHERE invoice_id = ?", (invoice_id,))
        except Exception:
            pass

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self._active_states: Dict[str, str] = {}
        self._transition_history: Dict[str, List[B2BStateTransition]] = {}
        self._init_db()

    def _get_conn(self):
        from backend.app.security import get_db_connection
        from backend.app.config import settings
        target_path = self.db_path or settings.DATABASE_PATH
        return get_db_connection(target_path)

    def _init_db(self):
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS b2b_fsm_states (
                        invoice_id TEXT PRIMARY KEY,
                        current_state TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS b2b_fsm_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        invoice_id TEXT NOT NULL,
                        from_state TEXT NOT NULL,
                        to_state TEXT NOT NULL,
                        trigger_event TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        metadata_json TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_fsm_inv ON b2b_fsm_history (invoice_id)")
                # Hydrate in-memory cache
                cursor = conn.cursor()
                cursor.execute("SELECT invoice_id, current_state FROM b2b_fsm_states")
                for row in cursor.fetchall():
                    self._active_states[row[0]] = row[1]
        except Exception as e:
            logger.warning(f"[B2B_FSM] DB init warning (using in-memory fallback): {e}")

    def get_state(self, invoice_id: str) -> str:
        if invoice_id in self._active_states:
            return self._active_states[invoice_id]
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT current_state FROM b2b_fsm_states WHERE invoice_id = ?", (invoice_id,))
            row = cursor.fetchone()
            if row:
                self._active_states[invoice_id] = row[0]
                return row[0]
        except Exception:
            pass
        return "OVERDUE"

    def transition(
        self,
        invoice_id: str,
        to_state: str,
        trigger_event: str,
        actor: str = "SYSTEM_AUTOMATION",
        metadata: Optional[Dict[str, Any]] = None
    ) -> B2BStateTransition:
        """
        Executes a validated state transition with durable SQLite WAL persistence. Raises ValueError on invalid transition.
        """
        current_state = self.get_state(invoice_id)

        if to_state not in self.STATES:
            raise ValueError(f"Unknown target state: {to_state}")

        allowed_targets = self.VALID_TRANSITIONS.get(current_state, set())
        if to_state not in allowed_targets:
            err_msg = f"Invalid state transition for invoice {invoice_id}: {current_state} -> {to_state}. Allowed: {allowed_targets}"
            logger.error(f"[B2B_FSM_VIOLATION] {err_msg}")
            raise ValueError(err_msg)

        now = time.time()
        transition_record = B2BStateTransition(
            invoice_id=invoice_id,
            from_state=current_state,
            to_state=to_state,
            trigger_event=trigger_event,
            actor=actor,
            timestamp=now,
            metadata=metadata or {}
        )

        self._active_states[invoice_id] = to_state
        if invoice_id not in self._transition_history:
            self._transition_history[invoice_id] = []
        self._transition_history[invoice_id].append(transition_record)

        # Durable SQLite persistence
        try:
            import json
            conn = self._get_conn()
            with conn:
                conn.execute("""
                    INSERT INTO b2b_fsm_states (invoice_id, current_state, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(invoice_id) DO UPDATE SET current_state = excluded.current_state, updated_at = excluded.updated_at
                """, (invoice_id, to_state, now))
                conn.execute("""
                    INSERT INTO b2b_fsm_history (invoice_id, from_state, to_state, trigger_event, actor, timestamp, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (invoice_id, current_state, to_state, trigger_event, actor, now, json.dumps(metadata or {})))
        except Exception as e:
            logger.error(f"[B2B_FSM_PERSISTENCE_ERROR] Failed to persist state for {invoice_id}: {e}")

        logger.info(f"[B2B_FSM] Invoice {invoice_id}: {current_state} -> {to_state} via {trigger_event}")
        return transition_record

    def get_history(self, invoice_id: str) -> List[B2BStateTransition]:
        if invoice_id in self._transition_history and self._transition_history[invoice_id]:
            return self._transition_history[invoice_id]
        # Query from DB if available
        try:
            import json
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT invoice_id, from_state, to_state, trigger_event, actor, timestamp, metadata_json
                FROM b2b_fsm_history WHERE invoice_id = ? ORDER BY id ASC
            """, (invoice_id,))
            records = []
            for row in cursor.fetchall():
                records.append(B2BStateTransition(
                    invoice_id=row[0],
                    from_state=row[1],
                    to_state=row[2],
                    trigger_event=row[3],
                    actor=row[4],
                    timestamp=row[5],
                    metadata=json.loads(row[6]) if row[6] else {}
                ))
            self._transition_history[invoice_id] = records
            return records
        except Exception:
            return []

b2b_fsm = B2BReceivablesStateMachine()
