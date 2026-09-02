import pytest
from backend.app.bulk_processor import bulk_processor
from backend.app.schemas import BulkRecoveryItem

SAMPLE_CSV = """payment_id,amount,error_code,error_description,customer_phone,customer_email,bank_code,method
pay_bulk_001,1500.0,GATEWAY_ERROR,HDFC bank timeout,+919876543210,cust1@example.com,HDFC,upi
pay_bulk_002,4500.0,INSUFFICIENT_FUNDS,Low account balance,+919876543211,cust2@example.com,SBI,card
pay_bulk_003,75000.0,HIGH_RISK_ANOMALY,Velocity spike fraud,+919876543212,cust3@example.com,ICICI,netbanking
pay_bulk_004,2200.0,TOKEN_REVOKED,Visa token expired,+919876543213,cust4@example.com,AXIS,card
"""

def test_bulk_csv_parsing():
    items = bulk_processor.parse_csv(SAMPLE_CSV)
    assert len(items) == 4
    assert items[0].payment_id == "pay_bulk_001"
    assert items[0].amount == 1500.0
    assert items[0].bank_code == "HDFC"
    assert items[2].amount == 75000.0

def test_bulk_batch_processing_and_policy():
    items = bulk_processor.parse_csv(SAMPLE_CSV)
    batch_res = bulk_processor.process_batch(items, merchant_id="merch_test_bulk")
    
    assert batch_res.total_processed == 4
    assert batch_res.total_batch_gmv_inr == 83200.0
    assert batch_res.recoverable_count >= 2
    # High risk 75,000 should be escalated
    assert batch_res.escalated_count >= 1
    assert batch_res.recovery_rate_pct > 0.0
    assert batch_res.processing_time_ms < 500.0 # Fast sub-second batching

def test_bulk_json_processing():
    items = [
        BulkRecoveryItem(
            payment_id="pay_json_01",
            amount=2000.0,
            error_code="GATEWAY_ERROR",
            bank_code="HDFC"
        ),
        BulkRecoveryItem(
            payment_id="pay_json_02",
            amount=3000.0,
            error_code="UPI_U30_DEGRADATION",
            bank_code="SBI"
        )
    ]
    res = bulk_processor.process_batch(items, merchant_id="merch_json_test")
    assert res.total_processed == 2
    assert res.recoverable_count == 2
