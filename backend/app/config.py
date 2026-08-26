import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    RAZORPAY_KEY_ID: str = Field(default="rzp_test_mock123456789")
    RAZORPAY_KEY_SECRET: str = Field(default="mock_razorpay_secret_key")
    RAZORPAY_WEBHOOK_SECRET: str = Field(default="whsec_mock_razorpay_webhook_secret")
    
    GEMINI_API_KEY: str = Field(default="mock_gemini_api_key")
    LLM_MODEL: str = Field(default="gemini-1.5-flash")
    
    ENVIRONMENT: str = Field(default="development")
    PORT: int = Field(default=8000)
    DATABASE_PATH: str = Field(default="recovery_audit.db")
    
    # Financial & Compliance Boundaries
    ENABLE_TRAI_COMPLIANCE: bool = Field(default=True)
    MAX_RETRY_ATTEMPTS: int = Field(default=3)
    MAX_DISCOUNT_PERCENT: float = Field(default=10.0)
    MAX_DISCOUNT_AMOUNT_INR: float = Field(default=500.0)
    HIGH_VALUE_THRESHOLD_INR: float = Field(default=50000.0)
    MIN_CONFIDENCE_THRESHOLD: float = Field(default=0.60)
    HIGH_VALUE_CONFIDENCE_THRESHOLD: float = Field(default=0.85)

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
