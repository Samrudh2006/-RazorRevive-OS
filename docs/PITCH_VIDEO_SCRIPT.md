# 🎙️ RazorRevive-OS: 5-Minute Pitch Video Script

> **Program:** Razorpay AI Buildathon 2026  
> **Track:** Track 03 — AI Revenue Recovery  
> **Candidate:** Samrudh  
> **Format:** 1080p Screen Recording with Webcam in Corner (OBS Studio / Loom)  
> **Target Duration:** Exactly 4 minutes 50 seconds (under 5-minute strict cap)

---

## ⏱️ Video Timeline & Scene-by-Scene Breakdown

```
[0:00 - 0:45] Scene 1: The Hook & Silent Margin Leak in Indian Fintech
[0:45 - 1:45] Scene 2: Three-Tier Bounded Architecture & Safety Guardrails
[1:45 - 3:30] Scene 3: LIVE DEMO (Fast-Loop Mandate Retry + B2B Voice PTP Lock)
[3:30 - 4:15] Scene 4: Held-Out 100-Batch Benchmark & Economic Cost Metrics
[4:15 - 5:00] Scene 5: What Broke & How We Got Out (Question #12) & Closing
```

---

### [0:00 – 0:45] Scene 1: The Hook & The Problem
**Visual On Screen:**  
*Title slide &rarr; Cut to live dashboard at `localhost:8000` with failing bank webhooks.*

**Spoken Script:**  
"Hi everyone, my name is Samrudh. In digital payments across India, revenue loss is almost never a sudden crash—it is a silent, persistent leak. 

Over 25% of transactions and recurring subscriptions fail due to transient bank downtime, customer 2FA drop-offs, or soft balance declines. Today, merchants make two fatal mistakes: they either retry blindly and hammer failing bank nodes—causing customer lockouts—or they do nothing and lose the customer forever.

Today, I’m presenting **RazorRevive-OS**: an autonomous, dual-loop revenue recovery engine built directly on Razorpay’s test APIs that prevents failure churn, executes mathematical Poisson mandate retries, and autonomously negotiates overdue B2B enterprise invoices."

---

### [0:45 – 1:45] Scene 2: Three-Tier Bounded Architecture
**Visual On Screen:**  
*Switch to `ARCHITECTURE.md` Mermaid Diagram showing Tier 1 (Ingestion) &rarr; Tier 2 (Diagnostic Kernel) &rarr; Tier 3 (Policy Gatekeeper).*

**Spoken Script:**  
"Before generating a single recovery action, we established a strict Three-Tier Financial Boundary Pattern.

First, our Ingestion Gateway cryptographically validates HMAC SHA-256 webhook signatures and acquires an atomic distributed mutex lock on `(merchant_id + payment_id)`—guaranteeing that even if 50 duplicate webhooks hit us during a network surge, only one action executes.

Second, our Diagnostic Kernel analyzes the failure metadata—distinguishing between transient bank gateway 503 timeouts, soft balance declines, and token expirations.

Third, our deterministic Policy Engine enforces hard legal boundaries: strictly blocking outbound customer messages during TRAI quiet hours between 9 PM and 9 AM IST, enforcing a hard 3-retry cap, and clamping discounts to under ₹500. The LLM never touches money movements without deterministic Pydantic schema validation."

---

### [1:45 – 3:30] Scene 3: Live Interactive Demonstration
**Visual On Screen:**  
*Split screen: FastAPI Terminal on left, Dark-Mode Web Dashboard on right.*

**Spoken Script:**  
"Let's see this in action. 

First, I'm going to simulate a sudden issuing bank degradation event on an HDFC node. As the webhook hits `/api/v1/webhooks/razorpay`, you can see the trace populate instantly. RazorRevive-OS diagnoses the transient gateway error and uses our Poisson recovery curve to schedule a smart mandate retry in 45 minutes—matching the bank's statistical recovery window.

Now, let's look at our Deep-Loop for high-value B2B enterprise invoices. 

Suppose a customer has an overdue ₹85,000 invoice and says: *'Sir invoice mein hamara GST number galat hai, correct GSTIN 29AABCU9603R1Z2 daal kar bhejiye.'* 

I trigger the voice turn: the agent detects the GST dispute, mutates the Razorpay Invoice in real-time via API, and re-issues the revised bill. When the customer confirms *'Accountant Friday ko payment clear kar dega'*, the system immediately registers an atomic **Promise-to-Pay (PTP) Lock**—suppressing annoying reminders and scheduling an automated Razorpay E-Mandate debit for Friday morning."

---

### [3:30 – 4:15] Scene 4: 100-Batch Benchmark & Economic Cost Metrics
**Visual On Screen:**  
*Terminal running `python benchmarks/benchmark_runner.py` & Dashboard Metrics Cards.*

**Spoken Script:**  
"To prove signal beyond cherry-picked examples, we evaluated RazorRevive-OS on a held-out synthetic test suite of 100 realistic payment failure edge cases.

Across 100 transactions representing over ₹10 Lakhs of at-risk GMV, our system achieved a **77.0% transaction recovery rate** and **88.6% recovery on bank outages**, rescuing **₹4,32,059 of revenue** with **zero double-deduction violations** and **100% TRAI quiet-hour compliance**. Our total intervention overhead was just ₹135."

---

### [4:15 – 5:00] Scene 5: What Broke & How We Got Out (Question #12)
**Visual On Screen:**  
*Code view of `backend/app/security.py` showing `DistributedIdempotencyStore`.*

**Spoken Script:**  
"Finally, what broke during our build? 

During high-concurrency stress testing with 50 replayed failure webhooks across a simulated bank outage spike, our decoupled async workers caused a race condition where multiple threads simultaneously processed the same customer drop-off, creating duplicate Razorpay Payment Links and exceeding rate limits.

We resolved this by engineering an atomic distributed mutex lock on `(merchant_id + payment_id)` backed by SQLite WAL-mode and an exponential jitter queue. Furthermore, we built a deterministic circuit breaker that halts dynamic outreach during systemic bank degradation, rerouting transactions to a deferred mandate queue.

RazorRevive-OS isn't just an AI demo—it is an auditable, production-ready recovery pipeline. The entire codebase, test suite, and architecture docs are open source on GitHub. Thank you, and I look forward to joining Razorpay in Bangalore this September!"
