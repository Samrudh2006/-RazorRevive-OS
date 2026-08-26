# 📋 Razorpay AI Buildathon: Official Application Form Answers (12 Items)

> **Application Form URL:** [https://forms.gle/d9r2gvxp8cmoZhon9](https://forms.gle/d9r2gvxp8cmoZhon9)  
> **Application Deadline:** 5 September 2026

---

### 1. Full Name
`Samrudh` *(Fill in your full name)*

### 2. College
`[Your College / University Name]`

### 3. Graduation Year
`2026` *(or your actual graduation year)*

### 4. In-person from September
`Yes`

### 5. 6 or 12 months: your pick
`12 months` *(Demonstrates maximum commitment to senior panel)*

### 6. Resume file
`[Upload clean 1-page PDF focused on Python, Systems, and AI Engineering]`

---

### 7. Your track
`Track 03 — AI Revenue Recovery`

### 8. Project name
`RazorRevive-OS: Autonomous Revenue Recovery & Smart Mandate Sentinel`

### 9. What it solves
`Detects failed digital payments, subscription halts, and overdue B2B enterprise invoices on Razorpay test APIs; diagnoses root causes (transient issuer gateway timeouts vs soft balance declines vs mandate drop-offs); and executes bounded recovery workflows (Poisson-distribution smart mandate retries, dynamic 1-click UPI recovery links, and conversational Hinglish voice negotiation with live invoice mutation) backed by an atomic distributed mutex and immutable audit ledger.`

### 10. GitHub repo URL, public
`https://github.com/Samrudh2006/Razorpay-Target-0.1percent-`

### 11. 5-min pitch video, unlisted is fine
`https://youtu.be/YOUR_UNLISTED_VIDEO_ID` *(Replace with your unlisted YouTube link)*

### 12. What broke, and how you got out
`During high-concurrency stress testing with 50 replayed failure webhooks across a simulated bank outage spike, our decoupled async workers caused an atomic race condition. Multiple worker threads simultaneously diagnosed the same customer drop-off before state locks were synchronized, creating duplicate Razorpay Payment Links and exceeding messaging rate limits.`

`We resolved this by engineering an atomic distributed mutex lock on (merchant_id + payment_id) backed by SQLite WAL-mode and an exponential jitter queue. Furthermore, we built a deterministic circuit breaker that halts dynamic outreach if bank health telemetry reports an active issuer degradation, rerouting transactions to a passive mandate retry queue instead.`
