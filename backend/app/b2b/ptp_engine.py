import sqlite3
import time
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from backend.app.config import settings
from backend.app.security import get_db_connection
from backend.app.schemas import PromiseToPayRecord

logger = logging.getLogger("RazorRevive.PTP")

class PTPStore:
    """
    Persistent Promise-to-Pay (PTP) Commitment Store & Notification Suppressor.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._init_db()

    def _init_db(self):
        conn = get_db_connection(self.db_path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ptp_commitments (
                    invoice_id TEXT PRIMARY KEY,
                    customer_contact TEXT NOT NULL,
                    promised_epoch REAL NOT NULL,
                    promised_window_label TEXT NOT NULL,
                    amount REAL NOT NULL,
                    timezone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    notes TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ptp_status ON ptp_commitments (status)")

    def register_promise(
        self,
        invoice_id: str,
        customer_contact: str,
        promised_epoch: float,
        promised_window_label: str,
        amount: float,
        notes: Optional[str] = None
    ) -> PromiseToPayRecord:
        self._init_db()
        conn = get_db_connection(self.db_path)
        now = time.time()
        
        record = PromiseToPayRecord(
            invoice_id=invoice_id,
            customer_contact=customer_contact,
            promised_epoch=promised_epoch,
            promised_window_label=promised_window_label,
            amount=amount,
            status="PROMISED",
            created_at=now,
            notes=notes
        )

        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO ptp_commitments (
                    invoice_id, customer_contact, promised_epoch,
                    promised_window_label, amount, timezone, status,
                    created_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.invoice_id,
                record.customer_contact,
                record.promised_epoch,
                record.promised_window_label,
                record.amount,
                record.timezone,
                record.status,
                record.created_at,
                record.notes
            ))

        logger.info(f"[PTP_REGISTERED] Invoice {invoice_id} locked until {promised_window_label} (Epoch: {promised_epoch})")
        return record

    def has_active_ptp_lock(self, invoice_id: str) -> bool:
        """
        Returns True if customer has an active promise-to-pay lock that has not expired.
        Used to strictly suppress redundant notifications.
        """
        self._init_db()
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        now = time.time()

        cursor.execute("""
            SELECT promised_epoch, status FROM ptp_commitments
            WHERE invoice_id = ? AND status IN ('PROMISED', 'SCHEDULED', 'DUE')
        """, (invoice_id,))
        
        row = cursor.fetchone()
        if not row:
            return False

        promised_epoch, status = row
        # Active if currently before the promised execution window + 2 hour grace period
        if now < (promised_epoch + 7200):
            return True
        return False

    def get_all_ptp_records(self) -> List[Dict[str, Any]]:
        self._init_db()
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ptp_commitments ORDER BY created_at DESC")
        rows = cursor.fetchall()
        records = []
        for r in rows:
            records.append({
                "invoice_id": r[0],
                "customer_contact": r[1],
                "promised_epoch": r[2],
                "promised_window_label": r[3],
                "amount": r[4],
                "timezone": r[5],
                "status": r[6],
                "created_at": r[7],
                "notes": r[8]
            })
        return records

ptp_store = PTPStore()
