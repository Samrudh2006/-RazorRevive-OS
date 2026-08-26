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
