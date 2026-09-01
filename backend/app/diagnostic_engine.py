import logging
from typing import Dict, Any, Optional, List
from backend.app.schemas import DiagnosisProposal, FailureClassType, RecoveryStrategyType

logger = logging.getLogger("RazorRevive.DiagnosticEngine")

class DiagnosticEngine:
    """
    AI Diagnosis & Root-Cause Classification Kernel.
    Classifies payment failures into structured FailureClass categories and proposes recovery strategies.
    
    SAFETY RULE: The diagnosis kernel NEVER executes payment operations. It only outputs a validated
    DiagnosisProposal that must be authorized by the deterministic PolicyEngine.
    """

    # Grounded Error Catalog mapping from Razorpay API Error Specs
    ERROR_CODE_MAP: Dict[str, Dict[str, Any]] = {
        "GATEWAY_ERROR": {
            "class": "TRANSIENT_GATEWAY",
            "strategy": "DELAYED_RETRY",
            "confidence": 0.94,
            "reasons": ["BANK_GATEWAY_TIMEOUT", "TRANSIENT_INFRASTRUCTURE_SPIKE"]
        },
        "SERVER_ERROR": {
            "class": "TRANSIENT_GATEWAY",
            "strategy": "DELAYED_RETRY",
            "confidence": 0.91,
            "reasons": ["INTERNAL_SERVER_ERROR", "ISSUER_UNAVAILABLE"]
        },
        "504_GATEWAY_TIMEOUT": {
            "class": "TRANSIENT_GATEWAY",
            "strategy": "DELAYED_RETRY",
            "confidence": 0.96,
            "reasons": ["HTTP_504_ISSUING_BANK_TIMEOUT"]
        },
        "PAYMENT_CARD_ISSUING_BANK_DEGRADED": {
            "class": "TRANSIENT_GATEWAY",
            "strategy": "DELAYED_RETRY",
            "confidence": 0.95,
            "reasons": ["BANK_NODE_DEGRADATION_REPORTED"]
        },
        "INSUFFICIENT_FUNDS": {
            "class": "INSUFFICIENT_FUNDS",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.92,
            "reasons": ["SOFT_BALANCE_DECLINE", "ALTERNATIVE_PAYMENT_REQUIRED"]
        },
        "BALANCE_LOW": {
            "class": "INSUFFICIENT_FUNDS",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.90,
            "reasons": ["ACCOUNT_BALANCE_INSUFFICIENT"]
        },
        "BAD_REQUEST_ERROR_LOW_BALANCE": {
            "class": "INSUFFICIENT_FUNDS",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.89,
            "reasons": ["BALANCE_BELOW_TRANSACTION_VALUE"]
        },
        "PAYMENT_EXPIRED": {
            "class": "EXPIRED_MANDATE",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.88,
            "reasons": ["MANDATE_TOKEN_EXPIRED", "RE_AUTHORIZATION_REQUIRED"]
        },
        "MANDATE_INACTIVE": {
            "class": "EXPIRED_MANDATE",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.91,
            "reasons": ["E_MANDATE_REGISTRATION_INACTIVE"]
        },
        "TOKEN_EXPIRED": {
            "class": "EXPIRED_MANDATE",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.93,
            "reasons": ["CARD_TOKENIZATION_EXPIRED"]
        },
        "PAYMENT_AUTHENTICATION_FAILED": {
            "class": "ABANDONED_AUTH",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.86,
            "reasons": ["CUSTOMER_ABANDONED_2FA_STEP", "OTP_TIMEOUT"]
        },
        "PAYMENT_CANCELLED_BY_USER": {
            "class": "ABANDONED_AUTH",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.92,
            "reasons": ["USER_DISMISSED_PAYMENT_MODAL"]
        },
        "OTP_EXPIRED": {
            "class": "ABANDONED_AUTH",
            "strategy": "DISPATCH_PAYMENT_LINK",
            "confidence": 0.89,
            "reasons": ["2FA_SESSION_EXPIRED"]
        },
        "SUSPICIOUS_VELOCITY": {
            "class": "SUSPICIOUS_VELOCITY",
            "strategy": "ESCALATE_HUMAN",
            "confidence": 0.95,
            "reasons": ["HIGH_TRANSACTION_VELOCITY_SPIKE", "CARD_TESTING_PATTERN"]
        },
        "HIGH_RISK_ANOMALY": {
            "class": "SUSPICIOUS_VELOCITY",
            "strategy": "ESCALATE_HUMAN",
            "confidence": 0.97,
            "reasons": ["GEOGRAPHIC_IP_MISMATCH", "SECURITY_RISK"]
        }
    }

    @classmethod
    def build_llm_prompt(
        cls,
        payment_id: str,
        amount: float,
        error_code: str,
        error_description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Builds a structured prompt adhering to JSON schema contracts for LLM inference.
        """
        system_prompt = (
            "You are RazorRevive-OS AI Diagnostic Kernel, an autonomous revenue recovery engine for Razorpay.\n"
            "Analyze the payment failure metadata and output a JSON object adhering to this schema:\n"
            "{\n"
            '  "failure_class": "TRANSIENT_GATEWAY" | "INSUFFICIENT_FUNDS" | "EXPIRED_MANDATE" | "ABANDONED_AUTH" | "SUSPICIOUS_VELOCITY",\n'
            '  "confidence": float (0.0 to 1.0),\n'
            '  "recommended_strategy": "DELAYED_RETRY" | "DISPATCH_PAYMENT_LINK" | "ESCALATE_HUMAN",\n'
            '  "reason_codes": [string],\n'
            '  "diagnostic_summary": string\n'
            "}\n"
            "SAFETY RULE: If fraud, velocity spike, or stolen card patterns are suspected, classify as SUSPICIOUS_VELOCITY with ESCALATE_HUMAN."
        )
        user_prompt = (
            f"Payment ID: {payment_id}\n"
            f"Amount: INR {amount}\n"
            f"Raw Error Code: {error_code}\n"
            f"Error Description: {error_description}\n"
            f"Metadata: {metadata or {}}"
        )
        return {"system": system_prompt, "user": user_prompt}

    @classmethod
    def diagnose(
        cls,
        payment_id: str,
        amount: float,
        error_code: str,
        error_description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DiagnosisProposal:
        """
        Diagnoses payment failure and outputs a validated Pydantic DiagnosisProposal.
        Uses deterministic semantic classification as primary/fallback logic.
        """
        meta = metadata or {}
        normalized_code = error_code.upper().strip()
        
        # Rule 1: Match against verified Razorpay Error Catalog
        matched_spec = cls.ERROR_CODE_MAP.get(normalized_code)
        
        if matched_spec:
            f_class: FailureClassType = matched_spec["class"]
            strategy: RecoveryStrategyType = matched_spec["strategy"]
            confidence: float = matched_spec["confidence"]
            reasons: List[str] = list(matched_spec["reasons"])
            requires_human: bool = (strategy == "ESCALATE_HUMAN")
            summary = f"Classified {normalized_code} as {f_class} with recommended strategy {strategy}."

        else:
            # Semantic Fallback Classifier based on error description
            desc_lower = error_description.lower()
            if any(term in desc_lower for term in ["timeout", "gateway", "504", "503", "bank down", "issuer unavailable"]):
                f_class = "TRANSIENT_GATEWAY"
                strategy = "DELAYED_RETRY"
                confidence = 0.82
                reasons = ["SEMANTIC_MATCH_BANK_TIMEOUT"]
                requires_human = False
                summary = "Semantic description matches transient issuing bank timeout."
            elif any(term in desc_lower for term in ["balance", "insufficient", "funds", "low balance"]):
                f_class = "INSUFFICIENT_FUNDS"
                strategy = "DISPATCH_PAYMENT_LINK"
                confidence = 0.85
                reasons = ["SEMANTIC_MATCH_INSUFFICIENT_FUNDS"]
                requires_human = False
                summary = "Semantic description matches soft balance decline."
            elif any(term in desc_lower for term in ["fraud", "suspicious", "velocity", "stolen", "risk"]):
                f_class = "SUSPICIOUS_VELOCITY"
                strategy = "ESCALATE_HUMAN"
                confidence = 0.90
                reasons = ["SEMANTIC_MATCH_HIGH_RISK"]
                requires_human = True
                summary = "Semantic description indicates risk/fraud anomaly."
            else:
                f_class = "ABANDONED_AUTH"
                strategy = "DISPATCH_PAYMENT_LINK"
                confidence = 0.65
                reasons = ["UNCLASSIFIED_DROP_OFF"]
                requires_human = False
                summary = "Unclassified payment decline; defaulting to alternate payment link proposal."

        # Pydantic schema validation guaranteed
        return DiagnosisProposal(
            payment_id=payment_id,
            amount=amount,
            raw_error_code=error_code,
            failure_class=f_class,
            confidence=confidence,
            recommended_strategy=strategy,
            reason_codes=reasons,
            requires_human=requires_human,
            diagnostic_summary=summary,
            model_version="recovery-diag-v1"
        )

diagnostic_engine = DiagnosticEngine()

