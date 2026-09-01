import os
import sys
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from benchmarks.dataset_generator import generate_held_out_benchmark_dataset
from benchmarks.benchmark_runner import run_held_out_benchmark

def test_dataset_generation(tmp_path):
    output_file = str(tmp_path / "test_100.json")
    records = generate_held_out_benchmark_dataset(output_path=output_file, sample_size=100)
    
    assert len(records) == 100
    assert os.path.exists(output_file)
    
    # Verify failure class distribution
    bank_errors = sum(1 for r in records if r["failure_class"] == "TRANSIENT_GATEWAY")
    insufficient = sum(1 for r in records if r["failure_class"] == "INSUFFICIENT_FUNDS")
    expired = sum(1 for r in records if r["failure_class"] == "EXPIRED_MANDATE")
    velocity = sum(1 for r in records if r["failure_class"] == "SUSPICIOUS_VELOCITY")
    
    assert bank_errors == 35
    assert insufficient == 25
    assert expired == 20
    assert velocity == 10

def test_benchmark_runner_execution(tmp_path):
    output_file = str(tmp_path / "test_100.json")
    results = run_held_out_benchmark(dataset_path=output_file)
    
    assert results["total_records"] == 100
    assert results["total_at_risk_gmv"] > 0
    assert results["recovered_gmv"] > 0
    assert results["recovered_count"] >= 70
    assert results["false_positive_overhead_inr"] > 0

def test_cli_replay_and_fuzz():
    from cli import cmd_replay, cmd_fuzz, cmd_roi
    from unittest.mock import MagicMock
    
    # 1. Test CLI Replay
    args_replay = MagicMock(case=1)
    code_replay = cmd_replay(args_replay)
    assert code_replay == 0
    
    # 2. Test CLI Fuzz
    args_fuzz = MagicMock(count=5)
    code_fuzz = cmd_fuzz(args_fuzz)
    assert code_fuzz == 0
    
    # 3. Test CLI ROI
    args_roi = MagicMock(gmv=10000000.0, failure_rate=12.5)
    code_roi = cmd_roi(args_roi)
    assert code_roi == 0

