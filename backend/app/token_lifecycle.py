import time
import logging
from typing import Dict, Any, List, Optional
from backend.app.schemas import CardTokenLifecycleRecord, CardTokenStatusType, CardNetworkType

logger = logging.getLogger("RazorRevive.TokenLifecycle")

class CardNetworkTokenLifecycleManager:
    """
    Card Network Tokenization Lifecycle & Revocation Manager (Phase 1, Phase 4, Phase 16).
    
    Models card network token states (Visa VTS, Mastercard MDES, RuPay Token) and prescribes
    precise, automated remediation strategies for expired cryptograms, token suspensions,
    revocations, and mandate deactivations.
    """

    ERROR_TOKEN_MAP: Dict[str, Dict[str, Any]] = {
        "TOKEN_REVOKED": {
            "status": "REVOKED",
            "action": "AUTOMATIC_TOKEN_REPROVISION",
            "retry_allowed": False,
            "reason": "Cardholder revoked token on issuer banking app; auto-reprovision requested."
        },
        "TOKEN_SUSPENDED": {
            "status": "SUSPENDED",
            "action": "STEP_UP_2FA_CONSENT",
            "retry_allowed": True,
            "reason": "Issuing bank temporary suspension; step-up authentication required."
        },
        "CARD_TOKEN_CRYPTOGRAM_INVALID": {
            "status": "CRYPTOGRAM_EXPIRED",
            "action": "AUTOMATIC_TOKEN_REPROVISION",
            "retry_allowed": False,
            "reason": "Single-use or time-bound cryptogram expired; fresh dynamic cryptogram needed."
        },
        "TOKEN_EXPIRED": {
            "status": "CRYPTOGRAM_EXPIRED",
            "action": "AUTOMATIC_TOKEN_REPROVISION",
            "retry_allowed": False,
            "reason": "Card network token registration expired."
        },
        "TOKEN_DELETED": {
            "status": "DELETED",
            "action": "CUSTOMER_PAYMENT_LINK",
            "retry_allowed": False,
            "reason": "Token deleted by merchant or user; new card enrollment required."
        },
        "MANDATE_INACTIVE": {
            "status": "REVOKED",
            "action": "CUSTOMER_PAYMENT_LINK",
            "retry_allowed": False,
            "reason": "Recurring e-mandate standing instruction inactive."
        }
    }

    def __init__(self):
        self._token_registry: Dict[str, CardTokenLifecycleRecord] = {}

    def inspect_token_error(
        self,
        token_id: str,
        error_code: str,
        card_network: CardNetworkType = "VISA_VTS",
        last_four: str = "4321"
    ) -> CardTokenLifecycleRecord:
        """Analyzes a card token failure code and generates a lifecycle remediation record."""
        normalized_code = error_code.upper().strip()
        spec = self.ERROR_TOKEN_MAP.get(normalized_code, {
            "status": "SUSPENDED",
            "action": "CUSTOMER_PAYMENT_LINK",
            "retry_allowed": False,
            "reason": f"Unclassified token error ({normalized_code})"
        })

        record = CardTokenLifecycleRecord(
            token_id=token_id,
            card_network=card_network,
            token_status=spec["status"],
            last_four_digits=last_four,
            expiry_month=12,
            expiry_year=2028,
            revocation_reason=spec["reason"],
            remediation_action=spec["action"],
            retry_allowed_on_token=spec["retry_allowed"],
            lifecycle_event_epoch=time.time()
        )

        self._token_registry[token_id] = record
        logger.info(f"[TOKEN_LIFECYCLE] Token {token_id} ({card_network}) marked as {record.token_status} -> Action: {record.remediation_action}")
        return record

    def get_token_record(self, token_id: str) -> Optional[CardTokenLifecycleRecord]:
        return self._token_registry.get(token_id)

card_token_manager = CardNetworkTokenLifecycleManager()
