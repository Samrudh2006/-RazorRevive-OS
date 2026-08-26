import sqlite3
import time
import json
import uuid
from typing import Optional, Dict, Any, List
from backend.app.config import settings

class AuditStore:
    """
    Immutable event ledger recording every diagnostic trace, boundary check, and API execution.
    Operating in SQLite WAL mode for high concurrency.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recovery_audit_ledger (
                    event_id TEXT PRIMARY KEY,
                    payment_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    raw_error_code TEXT,
                    failure_category TEXT,
                    confidence_score REAL,
                    policy_passed INTEGER NOT NULL,
                    action_taken TEXT NOT NULL,
                    recovery_status TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def record_event(
        self,
        payment_id: str,
        event_type: str,
        policy_passed: bool,
        action_taken: str,
        recovery_status: str,
        raw_error_code: Optional[str] = None,
        failure_category: Optional[str] = None,
        confidence_score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = time.time()
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO recovery_audit_ledger (
                        event_id, payment_id, timestamp, event_type,
                        raw_error_code, failure_category, confidence_score,
                        policy_passed, action_taken, recovery_status, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id,
                    payment_id,
                    now,
                    event_type,
                    raw_error_code,
                    failure_category,
                    confidence_score,
                    1 if policy_passed else 0,
                    action_taken,
                    recovery_status,
                    json.dumps(metadata or {})
                ))
            return event_id
        finally:
            conn.close()

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT * FROM recovery_audit_ledger ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def clear(self):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM recovery_audit_ledger")
        finally:
            conn.close()

audit_store = AuditStore()
