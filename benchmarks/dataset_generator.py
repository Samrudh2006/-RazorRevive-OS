import json
import random
import time
import os
from typing import List, Dict, Any

def generate_held_out_benchmark_dataset(
    output_path: str = "benchmarks/test_dataset_100.json",
    sample_size: int = 100,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Generates a reproducible, seeded benchmark dataset of 100 payment failure cases
    mapped from the official Razorpay Error Catalog and Indian payment failure distributions.
    """
    random.seed(seed)
    
    distribution = [
        {
            "category": "TRANSIENT_GATEWAY",
            "weight": 0.35, # 35 records
            "codes": ["GATEWAY_ERROR", "SERVER_ERROR", "504_GATEWAY_TIMEOUT", "PAYMENT_CARD_ISSUING_BANK_DEGRADED"],
            "descriptions": [
                "Bank gateway communication timeout on HDFC node",
                "SBI issuer bank latency spike 504",
                "ICICI netbanking session timed out during authorization",
                "Axis bank core banking system degraded"
            ],
            "amount_range": (1200.0, 8500.0),
            "expected_recovery_prob": 0.886
        },
        {
            "category": "INSUFFICIENT_FUNDS",
            "weight": 0.25, # 25 records
            "codes": ["INSUFFICIENT_FUNDS", "BALANCE_LOW", "BAD_REQUEST_ERROR_LOW_BALANCE"],
            "descriptions": [
                "Account balance insufficient for requested debit",
                "Soft decline: available balance below invoice amount",
                "Customer account balance insufficient for recurring subscription"
            ],
            "amount_range": (499.0, 3499.0),
            "expected_recovery_prob": 0.760
        },
        {
            "category": "EXPIRED_MANDATE",
            "weight": 0.20, # 20 records
            "codes": ["PAYMENT_EXPIRED", "MANDATE_INACTIVE", "TOKEN_EXPIRED"],
            "descriptions": [
                "Recurring mandate authorization token expired",
                "Customer debit card validity expired",
                "E-mandate registration cancelled or inactive"
            ],
            "amount_range": (999.0, 14999.0),
            "expected_recovery_prob": 0.700
        },
        {
            "category": "ABANDONED_AUTH",
            "weight": 0.10, # 10 records
            "codes": ["PAYMENT_AUTHENTICATION_FAILED", "PAYMENT_CANCELLED_BY_USER", "OTP_EXPIRED"],
            "descriptions": [
                "Customer closed browser window at 2FA SMS OTP step",
                "User cancelled payment intent prompt on mobile",
                "2FA authentication session timed out after 3 minutes"
            ],
            "amount_range": (1500.0, 24999.0),
            "expected_recovery_prob": 0.800
        },
        {
            "category": "SUSPICIOUS_VELOCITY",
            "weight": 0.10, # 10 records
            "codes": ["SUSPICIOUS_VELOCITY", "HIGH_RISK_ANOMALY"],
            "descriptions": [
                "High transaction velocity detected on newly registered IP",
                "Card testing pattern detected: 5 rapid declines in 60 seconds",
                "Geographic IP mismatch with shipping destination address"
            ],
            "amount_range": (15000.0, 85000.0),
            "expected_recovery_prob": 0.0 # Defense only
        }
    ]

    records = []
    record_idx = 1
    base_epoch = time.time() - (7 * 24 * 3600)

    for dist in distribution:
        count = int(dist["weight"] * sample_size)
        for _ in range(count):
            code = random.choice(dist["codes"])
            desc = random.choice(dist["descriptions"])
            amount = round(random.uniform(dist["amount_range"][0], dist["amount_range"][1]), 2)
            timestamp = base_epoch + random.randint(100, 7 * 24 * 3600)
            
            record = {
                "record_id": f"rec_{1000 + record_idx}",
                "payment_id": f"pay_bench_{random.randint(10000000, 99999999)}",
                "amount": amount,
                "error_code": code,
                "error_description": desc,
                "failure_class": dist["category"],
                "expected_recovery_prob": dist["expected_recovery_prob"],
                "customer_email": f"user_{record_idx}@example.com",
                "customer_phone": f"+9198{random.randint(10000000, 99999999)}",
                "timestamp": timestamp,
                "attempt_count": random.randint(1, 2)
            }
            records.append(record)
            record_idx += 1

    random.shuffle(records)

    dirname = os.path.dirname(output_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    return records

if __name__ == "__main__":
    records = generate_held_out_benchmark_dataset()
    print(f"Generated {len(records)} benchmark records.")
