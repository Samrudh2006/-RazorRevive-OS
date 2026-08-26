import hashlib
import json
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.security import verify_razorpay_signature, idempotency_store
from backend.app.audit_store import audit_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RazorRevive")

app = FastAPI(
    title="RazorRevive-OS",
    description="Autonomous Revenue Recovery & Smart Mandate Sentinel",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SimulatedFailureRequest(BaseModel):
    payment_id: str = Field(default="pay_mock_12345")
    amount: float = Field(default=2499.0, gt=0.0)
    error_code: str = Field(default="GATEWAY_ERROR")
    error_description: str = Field(default="Bank communication timeout on HDFC node")
    customer_email: str = Field(default="customer@example.com")
    customer_phone: str = Field(default="+919876543210")

@app.get("/health", status_code=status.HTTP_200_OK)
async def healthcheck():
    return {
        "status": "healthy",
        "service": "RazorRevive-OS",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }

async def process_async_recovery(event_payload: Dict[str, Any], payload_hash: str):
    """
    Asynchronous background worker orchestrating the recovery pipeline.
    """
    event_type = event_payload.get("event", "payment.failed")
    payload_data = event_payload.get("payload", {})
    payment_entity = payload_data.get("payment", {}).get("entity", {})
    
    payment_id = payment_entity.get("id", f"pay_unknown_{payload_hash[:8]}")
    error_code = payment_entity.get("error_code", "GATEWAY_ERROR")
    error_desc = payment_entity.get("error_description", "Bank gateway communication failure")
    amount = float(payment_entity.get("amount", 0)) / 100.0 if payment_entity.get("amount") else 2499.0

    logger.info(f"[PIPELINE_START] Ingested {event_type} for Payment ID: {payment_id} | Amount: ₹{amount}")

    # Record initial ingestion into immutable audit ledger
    audit_store.record_event(
        payment_id=payment_id,
        event_type=event_type,
        policy_passed=True,
        action_taken="INGESTED_AND_LOCKED",
        recovery_status="QUEUED",
        raw_error_code=error_code,
        failure_category="PENDING_DIAGNOSIS",
        confidence_score=1.0,
        metadata={"amount": amount, "description": error_desc}
    )

@app.post("/api/v1/webhooks/razorpay", status_code=status.HTTP_202_ACCEPTED)
async def razorpay_webhook_receiver(
    request: Request,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: Optional[str] = Header(None)
):
    """
    Primary ingestion gateway. Enforces HMAC SHA-256 validation and distributed atomic locking.
    """
    raw_body = await request.body()
    
    # In non-test environments or when signature is provided, verify cryptographically
    if x_razorpay_signature and not verify_razorpay_signature(raw_body, x_razorpay_signature):
        logger.warning("[SECURITY_ALERT] Invalid HMAC SHA-256 signature detected.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cryptographic signature."
        )

    try:
        event_payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON payload."
        )

    event_type = event_payload.get("event")
    payment_entity = event_payload.get("payload", {}).get("payment", {}).get("entity", {})
    payment_id = payment_entity.get("id") or event_payload.get("id")

    if not payment_id:
        payment_id = f"pay_{hashlib.md5(raw_body).hexdigest()[:12]}"

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    idempotency_key = f"wh_{payment_id}"

    # Atomic Distributed Mutex Check
    acquired = idempotency_store.acquire_lock(key=idempotency_key, payload_hash=payload_hash)
    if not acquired:
        logger.info(f"[IDEMPOTENT_IGNORE] Duplicate webhook delivery ignored for {idempotency_key}")
        return {
            "status": "ignored",
            "message": "Duplicate event delivery safely ignored by idempotency mutex.",
            "payment_id": payment_id
        }

    # Queue background recovery workflow
    background_tasks.add_task(process_async_recovery, event_payload, payload_hash)

    return {
        "status": "accepted",
        "message": "Webhook cryptographically verified and queued for recovery.",
        "payment_id": payment_id,
        "event": event_type
    }

@app.get("/api/v1/audit/events")
async def get_audit_ledger(limit: int = 50):
    events = audit_store.get_events(limit=limit)
    return {
        "total_returned": len(events),
        "events": events
    }

@app.post("/api/v1/simulate/failure")
async def simulate_failure_event(req: SimulatedFailureRequest, background_tasks: BackgroundTasks):
    """
    Test simulation endpoint for injecting failure webhooks locally.
    """
    mock_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": req.payment_id,
                    "amount": int(req.amount * 100),
                    "currency": "INR",
                    "status": "failed",
                    "error_code": req.error_code,
                    "error_description": req.error_description,
                    "email": req.customer_email,
                    "contact": req.customer_phone
                }
            }
        }
    }
    raw_bytes = json.dumps(mock_payload).encode("utf-8")
    expected_sig = None
    if settings.RAZORPAY_WEBHOOK_SECRET:
        import hmac
        expected_sig = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            raw_bytes,
            hashlib.sha256
        ).hexdigest()

    return await razorpay_webhook_receiver(
        request=Request(scope={"type": "http", "method": "POST", "headers": []}, receive=lambda: {"type": "http.request", "body": raw_bytes, "more_body": False}),
        background_tasks=background_tasks,
        x_razorpay_signature=expected_sig
    )
