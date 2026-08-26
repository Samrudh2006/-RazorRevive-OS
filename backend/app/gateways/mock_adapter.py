import time
from typing import Dict, Any, Optional
from backend.app.gateways.base import PaymentGateway

class MockPaymentGateway(PaymentGateway):
    """
    Hermetic Mock Payment Gateway for unit testing and offline demonstrations.
    Includes deterministic gateway-side idempotency ledger.
    """

    def __init__(self):
        self._gateway_records: Dict[str, Dict[str, Any]] = {}

    def create_recovery_link(
        self,
        payment_id: str,
        amount: float,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        discount_amount: float = 0.0,
        expire_by_minutes: int = 1440,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if idempotency_key and idempotency_key in self._gateway_records:
            record = self._gateway_records[idempotency_key].copy()
            record["idempotent_replay"] = True
            return record

        final_amount = max(1.0, round(amount - discount_amount, 2))
        res = {
            "success": True,
            "mode": "HERMETIC_MOCK",
            "payment_link_id": f"plink_mock_{payment_id}",
            "short_url": f"https://mockpay.local/i/{payment_id}",
            "final_amount": final_amount,
            "discount_applied": discount_amount,
            "expire_by": int(time.time()) + (expire_by_minutes * 60),
            "idempotent_replay": False
        }
        if idempotency_key:
            self._gateway_records[idempotency_key] = res
        return res

    def lookup_recovery_operation(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """
        Queries the gateway ledger using the deterministic idempotency key.
        Used for reconciliation when the application crashed in-flight before recording response.
        """
        return self._gateway_records.get(idempotency_key)

    def schedule_mandate_retry(
        self,
        mandate_id: str,
        amount: float,
        scheduled_epoch: float,
        attempt_count: int = 1,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if idempotency_key and idempotency_key in self._gateway_records:
            record = self._gateway_records[idempotency_key].copy()
            record["idempotent_replay"] = True
            return record

        res = {
            "success": True,
            "mode": "HERMETIC_MOCK",
            "mandate_id": mandate_id,
            "amount": amount,
            "scheduled_epoch": scheduled_epoch,
            "attempt_count": attempt_count,
            "status": "MOCK_SCHEDULED",
            "idempotent_replay": False
        }
        if idempotency_key:
            self._gateway_records[idempotency_key] = res
        return res

    def mutate_invoice(
        self,
        invoice_id: str,
        mutations: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "mode": "HERMETIC_MOCK",
            "invoice_id": invoice_id,
            "mutations_applied": mutations,
            "status": "MOCK_MUTATED"
        }

