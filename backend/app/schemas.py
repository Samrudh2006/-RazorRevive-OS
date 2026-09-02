from typing import Generic, TypeVar, Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
import time

T = TypeVar("T")

class ApiError(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable safe error message")
    details: Optional[Dict[str, Any]] = None

class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[ApiError] = None
    trace_id: str = Field(..., description="Distributed tracing identifier")
    timestamp: float = Field(default_factory=time.time)

# --- Core Recovery Schemas ---

FailureClassType = Literal[
    "TRANSIENT_GATEWAY",
    "INSUFFICIENT_FUNDS",
    "EXPIRED_MANDATE",
    "ABANDONED_AUTH",
    "SUSPICIOUS_VELOCITY"
]

RecoveryStrategyType = Literal[
    "DELAYED_RETRY",
    "DISPATCH_PAYMENT_LINK",
    "ESCALATE_HUMAN",
    "SUPPRESS"
]

class DiagnosisProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_id: str
    amount: float = Field(..., gt=0.0)
    raw_error_code: str
    failure_class: FailureClassType
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommended_strategy: RecoveryStrategyType
    reason_codes: List[str] = Field(default_factory=list)
    requires_human: bool = False
    diagnostic_summary: str = Field(..., max_length=500)
    model_version: str = "recovery-diag-v1"

class RetryWindowRecommendation(BaseModel):
    recommended_retry_delay_minutes: int = Field(ge=0, le=1440)
    success_probability: float = Field(ge=0.0, le=1.0)
    hazard_rate: float
    reason: str
    model_version: str = "recovery-hazard-v1"

class MutationProposal(BaseModel):
    invoice_id: str
    field_to_mutate: str
    old_value: Optional[str] = None
    new_value: str
    dispute_category: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool = True
    approved_by_policy: bool = False

class B2BStateTransition(BaseModel):
    invoice_id: str
    from_state: str
    to_state: str
    trigger_event: str
    actor: str
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class PromiseToPayRecord(BaseModel):
    invoice_id: str
    customer_contact: str
    promised_epoch: float
    promised_window_label: str
    amount: float
    timezone: str = "Asia/Kolkata"
    status: Literal["PROMISED", "SCHEDULED", "DUE", "DEBIT_ATTEMPT", "RECOVERED", "BREACHED", "ESCALATED"] = "PROMISED"
    created_at: float = Field(default_factory=time.time)
    notes: Optional[str] = None

class PolicyVerdict(BaseModel):
    passed_all_gates: bool
    verdict: Literal["ALLOWED", "DEFERRED_QUIET_HOURS", "ESCALATED_HUMAN", "SUPPRESSED"]
    violated_rules: List[str] = Field(default_factory=list)
    applied_modifications: List[str] = Field(default_factory=list)
    effective_discount: float = 0.0
    scheduled_epoch: Optional[float] = None

# --- Phase 1 & 8: NPCI Switch Telemetry & Live Degradation ---
SwitchHealthStateType = Literal["HEALTHY", "DEGRADED", "OUTAGE"]

class NPCISwitchStatus(BaseModel):
    bank_code: str = Field(..., description="Bank identifier (e.g. HDFC, SBI, ICICI, AXIS, KOTAK)")
    bank_name: str
    switch_state: SwitchHealthStateType
    success_rate_pct: float = Field(..., ge=0.0, le=100.0)
    avg_latency_ms: float = Field(..., ge=0.0)
    last_updated: float = Field(default_factory=time.time)
    active_incidents: List[str] = Field(default_factory=list)
    circuit_breaker_tripped: bool = False
    recommended_fallback_rail: Optional[str] = None

# --- Phase 1 & 4: Card Network Token Lifecycle (Visa VTS / Mastercard MDES / RuPay) ---
CardTokenStatusType = Literal["ACTIVE", "SUSPENDED", "REVOKED", "CRYPTOGRAM_EXPIRED", "DELETED"]
CardNetworkType = Literal["VISA_VTS", "MASTERCARD_MDES", "RUPAY_TOKEN", "GENERIC_NETWORK"]

class CardTokenLifecycleRecord(BaseModel):
    token_id: str
    card_network: CardNetworkType
    token_status: CardTokenStatusType
    last_four_digits: str
    expiry_month: int
    expiry_year: int
    revocation_reason: Optional[str] = None
    remediation_action: Literal[
        "AUTOMATIC_TOKEN_REPROVISION",
        "STEP_UP_2FA_CONSENT",
        "FALLBACK_UPI_INTENT",
        "CUSTOMER_PAYMENT_LINK"
    ] = "AUTOMATIC_TOKEN_REPROVISION"
    retry_allowed_on_token: bool = True
    lifecycle_event_epoch: float = Field(default_factory=time.time)

# --- Phase 2: Enterprise Bulk CSV Ingestion & Batch Recovery ---
class BulkRecoveryItem(BaseModel):
    payment_id: str
    amount: float
    error_code: str
    error_description: Optional[str] = ""
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    bank_code: Optional[str] = "HDFC"
    method: Optional[str] = "upi"

class BulkRecoveryBatchResponse(BaseModel):
    batch_id: str
    total_processed: int
    recoverable_count: int
    suppressed_count: int
    escalated_count: int
    projected_recovery_gmv_inr: float
    total_batch_gmv_inr: float
    recovery_rate_pct: float
    processing_time_ms: float
    items: List[Dict[str, Any]]

