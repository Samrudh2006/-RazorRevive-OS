# ARCHITECTURE SPECIFICATION: RazorRevive-OS

> **Track 03:** AI Revenue Recovery — Razorpay AI Buildathon 2026  
> **System Architecture Version:** 1.0.0 (Production-Grade)

---

## 1. System Overview

**RazorRevive-OS** is an autonomous, dual-loop revenue recovery and mandate orchestration engine designed to prevent and recover lost gross merchandise value (GMV) across digital payments, failed recurring subscriptions, and overdue B2B invoices.

The architecture enforces a **Three-Tier Financial Isolation Boundary Pattern**, ensuring that probabilistic LLM reasoning is strictly segregated from deterministic state execution, financial mutations, and regulatory compliance rules.

```mermaid
flowchart TD
    subgraph IngestionLayer [Tier 1: Ingestion & Telemetry Gateway]
        WH[Inbound Razorpay Webhook] --> SIG[HMAC SHA-256 Verifier]
        SIG --> MUTEX[Atomic Distributed Mutex: SQLite / Redis]
        MUTEX --> QUEUE[Async Normalizer & Event Buffer]
    end

    subgraph ReasoningLayer [Tier 2: Dual-Loop Reasoning Kernel]
        QUEUE --> CLASSIFIER[Root Cause Diagnostic Engine]
        CLASSIFIER -->|Fast-Loop: B2C / Subscriptions| FAST[Poisson Bank Uptime Retrier & 1-Click UPI Link]
        CLASSIFIER -->|Deep-Loop: High-Value B2B Invoices| DEEP[Hinglish Voice Agent & PTP State Machine]
    end

    subgraph BoundaryLayer [Tier 3: Policy & Financial Boundary Gatekeeper]
        FAST --> GATE{Deterministic Policy Engine}
        DEEP --> GATE
        GATE -->|TRAI Quiet Hours 9PM-9AM| DEFER[Scheduled Deferral Queue]
        GATE -->|Amount > ₹50K & Conf < 0.85| ESCALATE[Human CFO Queue]
        GATE -->|Confidence < 0.60| SUPPRESS[Safety Suppression]
        GATE -->|All Constraints Satisfied| EXEC[Razorpay API Dispatcher]
    end

    subgraph ExecutionLayer [Razorpay API & Persistence]
        EXEC --> RZP_PL[Payment Links API]
        EXEC --> RZP_MANDATE[Recurring Mandate Retries]
        EXEC --> RZP_INV[Dynamic Invoice Mutation API]
        EXEC --> AUDIT[(Immutable SQLite WAL Audit Ledger)]
    end
```

---

## 2. The Three-Tier Financial Boundary Pattern

### Tier 1: Ingestion & Telemetry Gateway
* **HMAC SHA-256 Webhook Verification:** Validates every incoming payload signature against the merchant webhook secret before any processing.
* **Distributed Atomic Mutex:** Acquires an atomic lock on `(merchant_id + payment_id)` with TTL to guarantee strict idempotency. Duplicate or out-of-order webhook replays are acknowledged with HTTP 200 and ignored.
* **Telemetry Aggregator:** Continuously ingests issuing bank health metrics to identify systemic degradation (e.g. HDFC 503 gateway drops).

### Tier 2: Dual-Loop Structured Reasoning Kernel
* **Fast-Loop (B2C & Subscriptions):** Classifies failure codes into Transient Bank Outages, Insufficient Balances, Expired Tokens, or Abandoned 2FA Sessions. Uses a Poisson arrival model to calculate the optimal retry timestamp $T_{\text{target}}$.
* **Deep-Loop (High-Ticket B2B Invoices > ₹25,000):** Engages client finance teams via low-latency conversational voice. Handles dispute objections (e.g., GST invoice mismatch) by dynamically mutating invoices via Razorpay APIs and locking a Promise-to-Pay (PTP) auto-debit timestamp.

### Tier 3: Deterministic Policy & Execution Gatekeeper
* Pure deterministic Python/Pydantic validation layer.
* Enforces TRAI contact quiet hours (9:00 PM – 9:00 AM IST), maximum 3-retry caps, dynamic discount caps (<10% or ₹500), and auto-escalates high-value transactions (>₹50,000) with confidence < 0.85 to human review.

---

## 3. Threat Model & Mitigation Matrix

| Threat Vector | Real-World Risk | Architectural Mitigation |
| :--- | :--- | :--- |
| **Webhook Replay Storms** | Duplicate payment links or double debit attempts when bank gateways retry webhooks. | **Atomic Distributed Mutex:** SQLite/Redis distributed lock with monotonic timestamp check rejects replays instantly. |
| **Thundering Herd on Bank Outage** | 100 failed transactions simultaneously retrying when bank servers reboot, causing instant re-failure. | **Exponential Backoff with Full Decorrelated Jitter:** Spreads retries across a Poisson distribution window. |
| **LLM Monetary Hallucination** | LLM generating unapproved discounts, altered amounts, or fake refund triggers. | **Strict Pydantic v2 Schema Enforcement:** Amount fields are immutable and passed directly from verified webhook payloads; discounts are clamped by hardcoded boundary rules. |
| **Regulatory & TRAI Violations** | Outbound messages sent to customers during late-night hours causing customer complaints. | **Deterministic Time-Window Gate:** Any outbound SMS/WhatsApp triggered between 21:00 and 09:00 IST is automatically deferred to 09:05 IST queue. |
| **Cascading Gateway 5xx Failures** | Razorpay or SMS APIs experiencing downtime. | **Stateful Circuit Breaker:** After 5 consecutive 5xx errors, enters `DEGRADED_MODE`, queues events to a local Dead-Letter Queue (DLQ), and alerts operators. |

---

## 4. State Machine Specification

```
[WEBHOOK_RECEIVED]
       │
       ▼
[SIGNATURE_VALIDATED] ──(Invalid)──► [HTTP 400 REJECT]
       │ (Valid)
       ▼
[IDEMPOTENCY_LOCK_ACQUIRED] ──(Duplicate)──► [HTTP 200 IDEMPOTENT_IGNORED]
       │ (Locked)
       ▼
[DIAGNOSING_ROOT_CAUSE]
       │
       ▼
[POLICY_BOUNDARY_CHECK]
       ├── (Quiet Hours) ──────────► [DEFERRED_QUEUE (09:05 IST)]
       ├── (Amount > ₹50K & Low Conf) ► [ESCALATED_HUMAN_QUEUE]
       ├── (Confidence < 0.60) ────► [SUPPRESSED]
       └── (Passed All Gates) ─────► [EXECUTING_INTERVENTION]
                                            │
                                            ▼
                               [RAZORPAY_API_DISPATCHED]
                                            │
                                            ▼
                               [AUDIT_LEDGER_COMMITTED]
```

---

## 5. Persistence & Audit Logging Specification

Every lifecycle event is recorded in an immutable SQLite database operating in **Write-Ahead Logging (WAL) mode**:

```sql
CREATE TABLE IF NOT EXISTS recovery_events (
    event_id TEXT PRIMARY KEY,
    payment_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    error_code TEXT NOT NULL,
    failure_category TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    policy_checks_passed INTEGER NOT NULL,
    action_taken TEXT NOT NULL,
    recovery_status TEXT NOT NULL,
    api_response_payload TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ptp_ledger (
    ptp_id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    promised_timestamp REAL NOT NULL,
    mandate_scheduled INTEGER NOT NULL,
    status TEXT NOT NULL
);
```
