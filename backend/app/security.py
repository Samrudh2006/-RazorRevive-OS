import hmac
import hashlib
import sqlite3
import time
import os
from typing import Optional
from backend.app.config import settings

def verify_razorpay_signature(raw_body: bytes, signature: Optional[str], secret: Optional[str] = None) -> bool:
    """
    Cryptographically validates incoming Razorpay webhook payload against merchant secret using HMAC SHA-256.
    """
    if not signature:
        return False
        
    webhook_secret = secret or settings.RAZORPAY_WEBHOOK_SECRET
    if not webhook_secret:
        return False
        
    expected_signature = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

class DistributedIdempotencyStore:
    """
    Thread-safe atomic distributed mutex store using SQLite WAL-mode.
    Prevents race conditions and double-charges when payment gateways replay webhooks.
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
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    payload_hash TEXT
                );
            """)

    def acquire_lock(self, key: str, payload_hash: Optional[str] = None, ttl_seconds: int = 3600) -> bool:
        """
        Attempts to atomically acquire an execution lock for a unique key (e.g. merchant_id + payment_id).
        Returns True if lock acquired (first time), False if duplicate/locked.
        """
        now = time.time()
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO idempotency_keys (key, created_at, status, payload_hash) VALUES (?, ?, ?, ?)",
                    (key, now, "LOCKED", payload_hash)
                )
                return True
        except sqlite3.IntegrityError:
            # Key exists: check if expired
            cursor = conn.execute("SELECT created_at, status FROM idempotency_keys WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                created_at, status = row
                if (now - created_at) > ttl_seconds:
                    with conn:
                        conn.execute(
                            "UPDATE idempotency_keys SET created_at = ?, status = ?, payload_hash = ? WHERE key = ?",
                            (now, "LOCKED", payload_hash, key)
                        )
                    return True
            return False
        finally:
            conn.close()

    def release_lock(self, key: str, status: str = "COMPLETED"):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("UPDATE idempotency_keys SET status = ? WHERE key = ?", (status, key))
        finally:
            conn.close()

    def clear(self):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM idempotency_keys")
        finally:
            conn.close()

idempotency_store = DistributedIdempotencyStore()
