import io
import csv
import time
import uuid
import logging
from typing import List, Dict, Any, Optional
from backend.app.schemas import BulkRecoveryItem, BulkRecoveryBatchResponse
from backend.app.diagnostic_engine import diagnostic_engine
from backend.app.recovery_optimizer import recovery_optimizer
from backend.app.policy_engine import policy_engine
from backend.app.audit_store import audit_store

logger = logging.getLogger("RazorRevive.BulkProcessor")

class EnterpriseBulkRecoveryProcessor:
    """
    Enterprise Bulk Ingestion & Batch Dispute Resolution Engine (Phase 2 & Phase 10).
    
    Processes CSV batches with hundreds or thousands of failed payment records,
    executes vector diagnosis, Weibull hazard analysis, and deterministic policy
    checks across each item, and generates exportable reconciliation summaries.
    """

    @classmethod
    def parse_csv(cls, csv_content: str) -> List[BulkRecoveryItem]:
        """Parses raw CSV string into a list of validated BulkRecoveryItem objects."""
        items: List[BulkRecoveryItem] = []
        reader = csv.DictReader(io.StringIO(csv_content))
        for idx, row in enumerate(reader):
            p_id = row.get("payment_id") or f"pay_bulk_{uuid.uuid4().hex[:8]}"
            try:
                amt = float(row.get("amount", 0.0))
            except (ValueError, TypeError):
                amt = 1000.0

            err_code = row.get("error_code") or "GATEWAY_ERROR"
            err_desc = row.get("error_description") or ""
            phone = row.get("customer_phone") or "+919876543210"
            email = row.get("customer_email") or "finance@merchant.com"
            bank = row.get("bank_code") or "HDFC"
            method = row.get("method") or "upi"

            items.append(BulkRecoveryItem(
                payment_id=p_id,
                amount=amt,
                error_code=err_code,
                error_description=err_desc,
                customer_phone=phone,
                customer_email=email,
                bank_code=bank,
                method=method
            ))
        return items

    @classmethod
    def process_batch(cls, items: List[BulkRecoveryItem], merchant_id: str = "merch_enterprise_default") -> BulkRecoveryBatchResponse:
        """Processes a batch of items and computes overall recovery metrics and audit records."""
        start_time = time.time()
        batch_id = f"batch_{uuid.uuid4().hex[:10]}"
        
        total_gmv = 0.0
        projected_recovered_gmv = 0.0
        recoverable_count = 0
        suppressed_count = 0
        escalated_count = 0
        processed_items: List[Dict[str, Any]] = []

        for item in items:
            total_gmv += item.amount
            
            # Tier 1 Diagnosis
            diag = diagnostic_engine.diagnose(
                payment_id=item.payment_id,
                amount=item.amount,
                error_code=item.error_code,
                error_description=item.error_description or "",
                metadata={"bank": item.bank_code, "method": item.method, "batch_id": batch_id}
            )

            # Recovery Hazard Window
            retry_rec = recovery_optimizer.select_optimal_retry_window(
                failure_class=diag.failure_class,
                attempt_number=1,
                bank_issuer=item.bank_code or "HDFC"
            )

            # Deterministic Policy Gatekeeper
            verdict = policy_engine.evaluate(
                diagnosis=diag,
                attempt_count=1,
                proposed_discount_pct=5.0 if diag.failure_class == "INSUFFICIENT_FUNDS" else 0.0
            )

            # Determine recovery feasibility
            if diag.recommended_strategy == "ESCALATE_HUMAN" or diag.requires_human or verdict.verdict == "ESCALATED_HUMAN":
                escalated_count += 1
                action_status = "ESCALATED_FINANCE_QUEUE"
            elif verdict.verdict == "ALLOWED" or verdict.verdict == "DEFERRED_QUIET_HOURS":
                recoverable_count += 1
                projected_recovered_gmv += item.amount * retry_rec.success_probability
                action_status = "SCHEDULED_RECOVERY"
            else:
                suppressed_count += 1
                action_status = "SUPPRESSED_POLICY"

            item_result = {
                "payment_id": item.payment_id,
                "amount": item.amount,
                "bank_code": item.bank_code,
                "failure_class": diag.failure_class,
                "confidence": diag.confidence,
                "strategy": diag.recommended_strategy,
                "retry_delay_minutes": retry_rec.recommended_retry_delay_minutes,
                "success_probability": retry_rec.success_probability,
                "policy_verdict": verdict.verdict,
                "action_status": action_status
            }
            processed_items.append(item_result)

            # Commit to hash-chained audit ledger
            audit_store.record_event(
                trace_id=f"tr_{batch_id}_{item.payment_id}",
                merchant_id=merchant_id,
                payment_id=item.payment_id,
                event_type="BATCH_RECOVERY_PROPOSAL",
                failure_class=diag.failure_class,
                decision=item_result,
                policy_verdict=verdict.verdict,
                action_taken=action_status,
                gateway_result={"batch_id": batch_id}
            )

        duration_ms = (time.time() - start_time) * 1000.0
        recovery_rate = (projected_recovered_gmv / total_gmv * 100.0) if total_gmv > 0 else 0.0

        logger.info(f"[BULK_PROCESSOR] Completed Batch {batch_id}: {len(items)} items processed in {duration_ms:.2f}ms | Recovery Rate: {recovery_rate:.2f}%")

        return BulkRecoveryBatchResponse(
            batch_id=batch_id,
            total_processed=len(items),
            recoverable_count=recoverable_count,
            suppressed_count=suppressed_count,
            escalated_count=escalated_count,
            projected_recovery_gmv_inr=round(projected_recovered_gmv, 2),
            total_batch_gmv_inr=round(total_gmv, 2),
            recovery_rate_pct=round(recovery_rate, 2),
            processing_time_ms=round(duration_ms, 2),
            items=processed_items
        )

bulk_processor = EnterpriseBulkRecoveryProcessor()
