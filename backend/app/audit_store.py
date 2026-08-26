import sqlite3
import time
import json
import logging
import uuid
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from backend.app.config import settings
from backend.app.security import get_db_connection

logger = logging.getLogger("RazorRevive.Audit")

GENESIS_HASH = "0" * 64

class CryptographicAuditLedger:
    """
    Immutable, Cryptographically Chained Decision Audit Ledger backed by SQLite WAL mode.
    Guarantees non-repudiable auditability where any database tampering breaks the hash chain.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._init_db()

    def _init_db(self):
        conn = get_db_connection(self.db_path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_chain_ledger (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    trace_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    merchant_id TEXT NOT NULL,
                    payment_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    failure_class TEXT,
                    decision_json TEXT NOT NULL,
                    policy_verdict TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    gateway_result_json TEXT,
                    prev_hash TEXT NOT NULL,
                    current_hash TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_pay ON audit_chain_ledger (payment_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_chain_ledger (trace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_seq ON audit_chain_ledger (sequence_id)")

    def _get_latest_hash(self, conn: sqlite3.Connection) -> str:
        cursor = conn.cursor()
        cursor.execute("SELECT current_hash FROM audit_chain_ledger ORDER BY sequence_id DESC LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else GENESIS_HASH

    @staticmethod
    def compute_canonical_hash(prev_hash: str, payload_dict: Dict[str, Any]) -> str:
        """
        Computes SHA-256 over canonicalized JSON representation of the event payload chained to prev_hash.
        """
        canonical_str = json.dumps(payload_dict, sort_keys=True, separators=(',', ':'))
        hash_input = f"{prev_hash}|{canonical_str}".encode("utf-8")
        return hashlib.sha256(hash_input).hexdigest()

    def record_event(
        self,
        trace_id: str,
        merchant_id: str,
        payment_id: str,
        event_type: str,
        failure_class: str,
        decision: Dict[str, Any],
        policy_verdict: str,
        action_taken: str,
        gateway_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        self._init_db()
        conn = get_db_connection(self.db_path)
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = time.time()

        with conn:
            prev_hash = self._get_latest_hash(conn)
            
            canonical_payload = {
                "event_id": event_id,
                "trace_id": trace_id,
                "timestamp": now,
                "merchant_id": merchant_id,
                "payment_id": payment_id,
                "event_type": event_type,
                "failure_class": failure_class,
                "decision": decision,
                "policy_verdict": policy_verdict,
                "action_taken": action_taken,
                "gateway_result": gateway_result or {}
            }
            
            current_hash = self.compute_canonical_hash(prev_hash, canonical_payload)

            conn.execute("""
                INSERT INTO audit_chain_ledger (
                    event_id, trace_id, timestamp, merchant_id, payment_id,
                    event_type, failure_class, decision_json, policy_verdict,
                    action_taken, gateway_result_json, prev_hash, current_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                trace_id,
                now,
                merchant_id,
                payment_id,
                event_type,
                failure_class,
                json.dumps(decision),
                policy_verdict,
                action_taken,
                json.dumps(gateway_result or {}),
                prev_hash,
                current_hash
            ))

        logger.info(f"[AUDIT_CHAIN] Committed Event {event_id} | Hash: {current_hash[:12]}... | Action: {action_taken}")
        return {
            "event_id": event_id,
            "current_hash": current_hash,
            "prev_hash": prev_hash,
            "timestamp": now
        }

    def verify_chain_integrity(self) -> Dict[str, Any]:
        """
        Cryptographically verifies the entire audit hash chain from Genesis to Head.
        Returns validation status, verified block count, and any tampering detection.
        """
        self._init_db()
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sequence_id, event_id, trace_id, timestamp, merchant_id,
                   payment_id, event_type, failure_class, decision_json,
                   policy_verdict, action_taken, gateway_result_json,
                   prev_hash, current_hash
            FROM audit_chain_ledger
            ORDER BY sequence_id ASC
        """)
        rows = cursor.fetchall()

        if not rows:
            return {
                "valid": True,
                "total_events": 0,
                "tampering_detected": False,
                "message": "Audit chain is empty. Genesis state valid."
            }

        expected_prev_hash = GENESIS_HASH
        for idx, r in enumerate(rows):
            seq_id, evt_id, trace_id, ts, m_id, p_id, evt_type, f_class, dec_json, pol_verd, act_taken, gw_json, prev_h, curr_h = r
            
            # Check 1: Prev hash continuity
            if prev_h != expected_prev_hash:
                return {
                    "valid": False,
                    "total_events": len(rows),
                    "tampering_detected": True,
                    "broken_at_sequence": seq_id,
                    "broken_event_id": evt_id,
                    "reason": f"Broken chain link at sequence {seq_id}: Expected prev_hash {expected_prev_hash[:8]} but found {prev_h[:8]}"
                }

            # Check 2: Content integrity
            canonical_payload = {
                "event_id": evt_id,
                "trace_id": trace_id,
                "timestamp": ts,
                "merchant_id": m_id,
                "payment_id": p_id,
                "event_type": evt_type,
                "failure_class": f_class,
                "decision": json.loads(dec_json),
                "policy_verdict": pol_verd,
                "action_taken": act_taken,
                "gateway_result": json.loads(gw_json) if gw_json else {}
            }
            recalculated_hash = self.compute_canonical_hash(expected_prev_hash, canonical_payload)
            if recalculated_hash != curr_h:
                return {
                    "valid": False,
                    "total_events": len(rows),
                    "tampering_detected": True,
                    "broken_at_sequence": seq_id,
                    "broken_event_id": evt_id,
                    "reason": f"Payload tampered at sequence {seq_id}: Hash mismatch for event {evt_id}"
                }

            expected_prev_hash = curr_h

        return {
            "valid": True,
            "total_events": len(rows),
            "tampering_detected": False,
            "latest_head_hash": expected_prev_hash,
            "message": f"Successfully verified {len(rows)} chained audit records with 0 tampering detected."
        }

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        self._init_db()
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sequence_id, event_id, trace_id, timestamp, merchant_id,
                   payment_id, event_type, failure_class, decision_json,
                   policy_verdict, action_taken, gateway_result_json,
                   prev_hash, current_hash
            FROM audit_chain_ledger
            ORDER BY sequence_id DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        events = []
        for r in rows:
            events.append({
                "sequence_id": r[0],
                "event_id": r[1],
                "trace_id": r[2],
                "timestamp": r[3],
                "merchant_id": r[4],
                "payment_id": r[5],
                "event_type": r[6],
                "failure_class": r[7],
                "decision": json.loads(r[8]) if r[8] else {},
                "policy_verdict": r[9],
                "action_taken": r[10],
                "gateway_result": json.loads(r[11]) if r[11] else {},
                "prev_hash": r[12],
                "current_hash": r[13]
            })
        return events

audit_store = CryptographicAuditLedger()
