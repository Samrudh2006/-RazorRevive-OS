from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class PaymentGateway(ABC):
    """
    Abstract Payment Gateway Interface.
    Decouples the revenue recovery control plane from any single underlying payment provider.
    """

    @abstractmethod
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
        """Creates a dynamic 1-click recovery payment link."""
        pass

    @abstractmethod
    def schedule_mandate_retry(
        self,
        mandate_id: str,
        amount: float,
        scheduled_epoch: float,
        attempt_count: int = 1
    ) -> Dict[str, Any]:
        """Schedules a recurring mandate retry attempt."""
        pass

    @abstractmethod
    def mutate_invoice(
        self,
        invoice_id: str,
        mutations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mutates an active invoice record (e.g. updating GSTIN/tax lines)."""
        pass
