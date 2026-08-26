from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "RazorRevive-OS"
    ENVIRONMENT: str = "sandbox"
    DEBUG: bool = True
    DATABASE_PATH: str = "recovery_audit.db"
    
    # Razorpay API Credentials
    RAZORPAY_KEY_ID: str = "rzp_test_mock12345"
    RAZORPAY_KEY_SECRET: str = "mock_secret_key_12345"
    RAZORPAY_WEBHOOK_SECRET: str = "whsec_mock_signature_test"

    # LLM / Gemini Credentials
    GEMINI_API_KEY: Optional[str] = None
    
    # Financial & Compliance Guardrail Boundaries
    MAX_RETRY_ATTEMPTS: int = 3
    MAX_DISCOUNT_PERCENT: float = 10.0
    MAX_DISCOUNT_AMOUNT_INR: float = 500.0
    HIGH_VALUE_THRESHOLD_INR: float = 50000.0
    HIGH_VALUE_CONFIDENCE_THRESHOLD: float = 0.85
    MIN_CONFIDENCE_THRESHOLD: float = 0.60
    
    # TRAI Quiet-Hours Enforcement
    ENABLE_TRAI_COMPLIANCE: bool = True
    TRAI_QUIET_START_HOUR_IST: int = 21 # 9:00 PM IST
    TRAI_QUIET_END_HOUR_IST: int = 9   # 9:00 AM IST

settings = Settings()
