import time
from typing import Dict, Any
from backend.app.gateways.base import PaymentGateway

class MockPaymentGateway(PaymentGateway):
    """
    Hermetic Mock Payment Gateway for unit testing and offline demonstrations.
    """

    def create_recovery_link(
        self,
        payment_id: str,
        amount: float,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        discount_amount: float = 0.0,
        expire_by_minutes: int = 1440
    ) -> Dict[str, Any]:
        final_amount = max(1.0, round(amount - discount_amount, 2))
        return {
            "success": True,
            "mode": "HERMETIC_MOCK",
            "payment_link_id": f"plink_mock_{payment_id}",
            "short_url": f"https://mockpay.local/i/{payment_id}",
            "final_amount": final_amount,
            "discount_applied": discount_amount,
            "expire_by": int(time.time()) + (expire_by_minutes * 60)
        }

    def schedule_mandate_retry(
        self,
        mandate_id: str,
        amount: float,
        scheduled_epoch: float,
        attempt_count: int = 1
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "mode": "HERMETIC_MOCK",
            "mandate_id": mandate_id,
            "amount": amount,
            "scheduled_epoch": scheduled_epoch,
            "attempt_count": attempt_count,
            "status": "MOCK_SCHEDULED"
        }

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
