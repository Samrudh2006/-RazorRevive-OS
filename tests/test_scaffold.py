import os
import pytest
from backend.app import __version__
from backend.app.config import settings

def test_version_and_metadata():
    assert __version__ == "1.0.0"

def test_default_boundary_settings():
    assert settings.ENABLE_TRAI_COMPLIANCE is True
    assert settings.MAX_RETRY_ATTEMPTS == 3
    assert settings.MAX_DISCOUNT_PERCENT == 10.0
    assert settings.MAX_DISCOUNT_AMOUNT_INR == 500.0
    assert settings.HIGH_VALUE_THRESHOLD_INR == 50000.0
    assert settings.MIN_CONFIDENCE_THRESHOLD == 0.60
    assert settings.HIGH_VALUE_CONFIDENCE_THRESHOLD == 0.85

def test_architecture_documentation_exists():
    arch_path = os.path.join(os.path.dirname(__file__), "..", "ARCHITECTURE.md")
    assert os.path.exists(arch_path)
    with open(arch_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Three-Tier Financial Isolation Boundary Pattern" in content
        assert "HMAC SHA-256" in content
        assert "Poisson" in content
