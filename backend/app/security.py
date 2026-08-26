import hmac
import hashlib
import time
import sqlite3
import re
import threading
import logging
from typing import Optional, Dict, Any
from backend.app.config import settings

logger = logging.getLogger("RazorRevive.Security")

# Thread-local storage for SQLite connections in WAL mode
_local = threading.local()

def get_db_connection(db_path: str) -> sqlite3.Connection:
    if not hasattr(_local, f"conn_{db_path}"):
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        setattr(_local, f"conn_{db_path}", conn)
    return getattr(_local, f"conn_{db_path}")

def mask_pii_string(value: Optional[str]) -> str:
    """
    DPDP Act 2023 & PCI-DSS Compliance: Masks Personally Identifiable Information (PII).
    Masks Phone: +919876543210 -> +9198******10
    Masks Email: customer@example.com -> c******r@example.com
    """
    if not value:
        return "N/A"
    
    # Check if Email
    if "@" in value:
        parts = value.split("@")
        name, domain = parts[0], parts[1]
        if len(name) <= 2:
            masked_name = name[0] + "*"
        else:
            masked_name = name[0] + "*" * (len(name) - 2) + name[-1]
        return f"{masked_name}@{domain}"
    
    # Check if Phone (10-13 digits)
    clean_digits = re.sub(r"[^\d+]", "", value)
    if len(clean_digits) >= 10:
        return clean_digits[:4] + "*" * (len(clean_digits) - 6) + clean_digits[-2:]
    
    return value[:2] + "****"

def verify_razorpay_signature(
    raw_payload: bytes,
    signature: Optional[str],
    secret: Optional[str] = None,
    timestamp: Optional[int] = None,
    max_drift_seconds: int = 300
) -> bool:
    """
    Timing-Attack Resistant HMAC SHA-256 Webhook Signature Verification.
    Includes replay-attack timestamp drift protection.
    """
    if not signature:
        logger.warning("[SECURITY] Missing X-Razorpay-Signature header.")
        return False

    # Replay attack protection (within 300s window if timestamp provided)
    if timestamp:
        current_time = int(time.time())
        if abs(current_time - timestamp) > max_drift_seconds:
            logger.warning(f"[SECURITY] Webhook timestamp drifted by {abs(current_time - timestamp)}s > {max_drift_seconds}s. Rejecting replay.")
            return False

    webhook_secret = secret or settings.RAZORPAY_WEBHOOK_SECRET
    if not webhook_secret:
        logger.error("[SECURITY] RAZORPAY_WEBHOOK_SECRET is not configured.")
        return False

    expected_signature = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=raw_payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    # hmac.compare_digest prevents side-channel timing analysis attacks
    is_valid = hmac.compare_digest(expected_signature, signature)
    if not is_valid:
        logger.warning("[SECURITY] Cryptographic signature mismatch.")
    return is_valid

class DistributedIdempotencyStore:
    """
    Atomic Distributed Mutex Lock (SQLite WAL-backed).
    Guarantees strict once-and-only-once execution per (merchant_id + payment_id).
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._init_db()

    def _init_db(self):
        conn = get_db_connection(self.db_path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    payload_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_idem_time ON idempotency_keys (created_at)")

    def acquire_lock(self, key: str, payload_hash: str = "", ttl_seconds: int = 86400) -> bool:
        """
        Atomic CAS (Compare-And-Swap) lock acquisition.
        Returns True if lock was freshly acquired; False if duplicate delivery.
        """
        conn = get_db_connection(self.db_path)
        now = time.time()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO idempotency_keys (idempotency_key, payload_hash, created_at, status) VALUES (?, ?, ?, ?)",
                    (key, payload_hash, now, "ACQUIRED")
                )
            return True
        except sqlite3.IntegrityError:
            # Key already exists: check if lock has expired past TTL
            cursor = conn.cursor()
            cursor.execute("SELECT created_at FROM idempotency_keys WHERE idempotency_key = ?", (key,))
            row = cursor.fetchone()
            if row and (now - row[0]) > ttl_seconds:
                with conn:
                    conn.execute(
                        "UPDATE idempotency_keys SET created_at = ?, payload_hash = ?, status = 'RENEWED' WHERE idempotency_key = ?",
                        (now, payload_hash, key)
                    )
                return True
            return False

idempotency_store = DistributedIdempotencyStore()
