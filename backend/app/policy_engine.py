import time
import logging
from typing import Dict, Any, Tuple, Optional, List
from pydantic import BaseModel, Field
from backend.app.config import settings
from backend.app.schemas import DiagnosisProposal, PolicyVerdict

logger = logging.getLogger("RazorRevive.PolicyEngine")

class PolicyEngine:
    """
    Deterministic Financial Boundary & Compliance Gatekeeper (Tier 3).
    The ironclad safety layer between probabilistic AI proposals and financial execution.
    """

    @classmethod
    def is_trai_quiet_hours(cls, current_epoch: Optional[float] = None) -> bool:
        """
        TRAI Compliance: Commercial communications are legally prohibited between 9:00 PM (21:00) and 9:00 AM (09:00) IST.
        """
        if not settings.ENABLE_TRAI_COMPLIANCE:
            return False

        epoch = current_epoch or time.time()
        ist_offset_sec = 5.5 * 3600  # UTC+5:30
        ist_struct = time.gmtime(epoch + ist_offset_sec)
        hour = ist_struct.tm_hour

        # Quiet hours: 21:00 (9 PM) to 08:59 (before 9 AM)
        if hour >= settings.TRAI_QUIET_START_HOUR_IST or hour < settings.TRAI_QUIET_END_HOUR_IST:
            return True
        return False

    @classmethod
    def calculate_next_trai_active_window(cls, current_epoch: Optional[float] = None) -> float:
        """
        Calculates the next legal 09:05 AM IST timestamp to resume deferred messages.
        """
        epoch = current_epoch or time.time()
        ist_offset_sec = 5.5 * 3600
        ist_struct = time.gmtime(epoch + ist_offset_sec)
        
        day_offset = 1 if ist_struct.tm_hour >= settings.TRAI_QUIET_START_HOUR_IST else 0
        target_struct = time.struct_time((
            ist_struct.tm_year, ist_struct.tm_mon, ist_struct.tm_mday + day_offset,
            settings.TRAI_QUIET_END_HOUR_IST, 5, 0, 0, 0, -1
        ))
        target_epoch_ist = time.mktime(target_struct)
        return target_epoch_ist - ist_offset_sec

    @classmethod
    def clamp_recovery_discount(cls, transaction_amount: float, proposed_discount_pct: float = 0.0) -> float:
        """
        Hard Financial Cap: Limits dynamic customer incentives to <= MAX_DISCOUNT_PERCENT (10%) and <= MAX_DISCOUNT_AMOUNT_INR (₹500).
        """
        pct_capped = min(proposed_discount_pct, settings.MAX_DISCOUNT_PERCENT)
        calculated_amount = (pct_capped / 100.0) * transaction_amount
        final_discount = min(calculated_amount, settings.MAX_DISCOUNT_AMOUNT_INR)
        return max(0.0, round(final_discount, 2))

    @classmethod
    def evaluate(
        cls,
        diagnosis: DiagnosisProposal,
        attempt_count: int = 1,
        proposed_discount_pct: float = 0.0,
        channel: str = "WHATSAPP",
        current_epoch: Optional[float] = None
    ) -> PolicyVerdict:
        """
        Evaluates a candidate diagnostic proposal against all deterministic policy rules.
        """
        violated_rules: List[str] = []
        applied_modifications: List[str] = []
        verdict = "ALLOWED"
        scheduled_epoch = None

        # Gate 1: Hard Retry Limit (Max 3 attempts)
        if attempt_count > settings.MAX_RETRY_ATTEMPTS:
            violated_rules.append(f"MAX_RETRIES_EXCEEDED (Attempt {attempt_count} > {settings.MAX_RETRY_ATTEMPTS})")
            applied_modifications.append("Action suppressed due to maximum retry threshold reached.")
            return PolicyVerdict(
                passed_all_gates=False,
                verdict="SUPPRESSED",
                violated_rules=violated_rules,
                applied_modifications=applied_modifications
            )

        # Gate 2: Minimum Confidence Cutoff (< 0.60 -> Suppress)
        if diagnosis.confidence < settings.MIN_CONFIDENCE_THRESHOLD:
            violated_rules.append(f"CONFIDENCE_TOO_LOW ({diagnosis.confidence:.2f} < {settings.MIN_CONFIDENCE_THRESHOLD:.2f})")
            applied_modifications.append("Action suppressed due to low diagnostic confidence.")
            return PolicyVerdict(
                passed_all_gates=False,
                verdict="SUPPRESSED",
                violated_rules=violated_rules,
                applied_modifications=applied_modifications
            )

        # Gate 3: High-Value Anomaly Escalation (> ₹50,000 and confidence < 0.85)
        if diagnosis.amount > settings.HIGH_VALUE_THRESHOLD_INR and diagnosis.confidence < settings.HIGH_VALUE_CONFIDENCE_THRESHOLD:
            violated_rules.append(f"HIGH_VALUE_UNCERTAIN_ANOMALY (INR {diagnosis.amount:,.2f} > INR {settings.HIGH_VALUE_THRESHOLD_INR:,.2f} & Conf {diagnosis.confidence:.2f} < {settings.HIGH_VALUE_CONFIDENCE_THRESHOLD:.2f})")
            applied_modifications.append("Rerouted to Human CFO Queue.")
            return PolicyVerdict(
                passed_all_gates=False,
                verdict="ESCALATED_HUMAN",
                violated_rules=violated_rules,
                applied_modifications=applied_modifications
            )

        # Gate 4: TRAI Quiet-Hours Enforcement (Outbound messaging blocked between 9 PM and 9 AM IST)
        if diagnosis.recommended_strategy == "DISPATCH_PAYMENT_LINK" and channel.upper() in ["WHATSAPP", "SMS"]:
            if cls.is_trai_quiet_hours(current_epoch):
                violated_rules.append("TRAI_QUIET_HOURS_VIOLATION (21:00 - 09:00 IST)")
                scheduled_epoch = cls.calculate_next_trai_active_window(current_epoch)
                applied_modifications.append(f"Outreach deferred to next legal 09:05 AM IST window (Epoch: {scheduled_epoch}).")
                verdict = "DEFERRED_QUIET_HOURS"

        # Gate 5: Discount Boundary Clamp
        discount_amount = cls.clamp_recovery_discount(diagnosis.amount, proposed_discount_pct)
        if discount_amount > 0:
            applied_modifications.append(f"Applied clamped discount: INR {discount_amount:,.2f}")

        passed = (len(violated_rules) == 0 or verdict == "DEFERRED_QUIET_HOURS")

        return PolicyVerdict(
            passed_all_gates=passed,
            verdict=verdict,
            violated_rules=violated_rules,
            applied_modifications=applied_modifications,
            effective_discount=discount_amount,
            scheduled_epoch=scheduled_epoch
        )

policy_engine = PolicyEngine()
