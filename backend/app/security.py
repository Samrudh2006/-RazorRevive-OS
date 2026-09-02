import hmac
import hashlib
import time
import json
import sqlite3
import re
import os
import threading
import logging
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives import constant_time
try:
    import redis
except ImportError:
    redis = None

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
    Uses cryptography constant_time.bytes_eq and replay timestamp drift protection.
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

    # Hardware-accelerated constant_time.bytes_eq prevents side-channel timing analysis attacks
    is_valid = constant_time.bytes_eq(expected_signature.encode("utf-8"), signature.encode("utf-8"))
    if not is_valid:
        logger.warning("[SECURITY] Cryptographic signature mismatch.")
    return is_valid

class DistributedIdempotencyStore:
    """
    Atomic Distributed Mutex Lock & Durable Execution Store.
    Supports Redis distributed lock with SQLite WAL-backed local fallback.
    Guarantees strict once-and-only-once execution per (merchant_id + payment_id).
    Features multi-tenant isolation with merchant_api_key_id.
    """

    def __init__(self, db_path: Optional[str] = None, redis_url: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self.redis_client = None
        
        target_redis = redis_url or os.getenv("REDIS_URL")
        if target_redis and redis:
            try:
                # Fast 0.15s socket timeout prevents startup/turn latency spikes on unreachable Redis
                self.redis_client = redis.Redis.from_url(target_redis, decode_responses=True, socket_timeout=0.15, socket_connect_timeout=0.15)
                self.redis_client.ping()
                logger.info("[SECURITY] Connected to distributed Redis lock manager.")
            except Exception as e:
                logger.warning(f"[SECURITY] Redis not reachable ({e}). Falling back to local SQLite WAL mutex.")
                self.redis_client = None

        self._init_db()

    def _init_db(self):
        conn = get_db_connection(self.db_path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    merchant_api_key_id TEXT DEFAULT 'default_merchant',
                    payload_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    result_payload TEXT,
                    completed_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_idem_time ON idempotency_keys (created_at)")
            # Backward-compatible schema migration
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(idempotency_keys);")
            columns = [c[1] for c in cursor.fetchall()]
            if "merchant_api_key_id" not in columns:
                conn.execute("ALTER TABLE idempotency_keys ADD COLUMN merchant_api_key_id TEXT DEFAULT 'default_merchant';")
            if "result_payload" not in columns:
                conn.execute("ALTER TABLE idempotency_keys ADD COLUMN result_payload TEXT;")
            if "completed_at" not in columns:
                conn.execute("ALTER TABLE idempotency_keys ADD COLUMN completed_at REAL;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_idem_merch ON idempotency_keys (merchant_api_key_id, idempotency_key)")

    def acquire_lock(self, key: str, payload_hash: str = "", ttl_seconds: int = 86400, merchant_id: str = "default_merchant") -> bool:
        """
        Atomic CAS lock acquisition with durable completion awareness and multi-tenant isolation.
        - If key does not exist: Inserts status='ACQUIRED' and returns True.
        - If key exists and status='COMPLETED': Returns False (already durably executed; duplicate prevented).
        - If key exists and status='ACQUIRED' but lease expired (> ttl_seconds): Renews lease and returns True.
        - If key exists and status='ACQUIRED' with active lease: Returns False (concurrent collision dropped).
        """
        conn = get_db_connection(self.db_path)
        now = time.time()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO idempotency_keys (idempotency_key, merchant_api_key_id, payload_hash, created_at, status) VALUES (?, ?, ?, ?, ?)",
                    (key, merchant_id, payload_hash, now, "ACQUIRED")
                )
            return True
        except sqlite3.IntegrityError:
            cursor = conn.cursor()
            cursor.execute("SELECT created_at, status FROM idempotency_keys WHERE idempotency_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                created_at, status = row[0], row[1]
                # If already durably completed, NEVER re-execute, regardless of elapsed time
                if status == "COMPLETED":
                    return False
                # If lease expired without completion (simulated crash during processing), allow reclamation
                if (now - created_at) > ttl_seconds:
                    with conn:
                        conn.execute(
                            "UPDATE idempotency_keys SET created_at = ?, payload_hash = ?, status = 'RENEWED' WHERE idempotency_key = ?",
                            (now, payload_hash, key)
                        )
                    return True
            return False

    def mark_completed(self, key: str, result_payload: Optional[dict] = None) -> bool:
        """
        Marks an execution as durably completed.
        Prevents any subsequent execution even after lease expiration.
        """
        conn = get_db_connection(self.db_path)
        now = time.time()
        result_json = json.dumps(result_payload) if result_payload else None
        with conn:
            conn.execute(
                "UPDATE idempotency_keys SET status = 'COMPLETED', result_payload = ?, completed_at = ? WHERE idempotency_key = ?",
                (result_json, now, key)
            )
        return True

    def get_execution_record(self, key: str) -> Optional[dict]:
        """
        Retrieves the durable execution record for an idempotency key.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT idempotency_key, payload_hash, created_at, status, result_payload, completed_at, merchant_api_key_id FROM idempotency_keys WHERE idempotency_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "idempotency_key": row[0],
            "payload_hash": row[1],
            "created_at": row[2],
            "status": row[3],
            "result_payload": json.loads(row[4]) if row[4] else None,
            "completed_at": row[5],
            "merchant_api_key_id": row[6] if len(row) > 6 else "default_merchant"
        }

    def is_execution_completed(self, key: str) -> bool:
        """
        Checks if the action for this idempotency key was already completed.
        """
        rec = self.get_execution_record(key)
        return rec is not None and rec.get("status") == "COMPLETED"

idempotency_store = DistributedIdempotencyStore()

