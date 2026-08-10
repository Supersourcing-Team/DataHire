from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "DataHire"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # LinkedIn OAuth
    LINKEDIN_CLIENT_ID: str
    LINKEDIN_CLIENT_SECRET: str
    LINKEDIN_REDIRECT_URI: str
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    # Google Gemini AI
    GEMINI_API_KEY: str
    
    # AWS
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: Optional[str] = None
    
    # Redis (for caching)
    REDIS_URL: Optional[str] = None
    
    # Email
    EMAIL_PROVIDER: str = "ses"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "ayush@supersourcing.com"
    
    # SendGrid
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "ayush@supersourcing.com"
    SENDGRID_FROM_NAME: str = "DataHire"

    # AWS SES
    SES_FROM_EMAIL: str = "admin@datahire.ai"
    SES_AWS_ACCESS_KEY_ID: Optional[str] = None
    SES_AWS_SECRET_ACCESS_KEY: Optional[str] = None
    SES_AWS_REGION: Optional[str] = None

    # Telnyx SMS
    TELNYX_API_KEY: Optional[str] = None
    TELNYX_FROM_PHONE: Optional[str] = None
    
    # CORS
    ALLOWED_ORIGINS: list = ["http://localhost:3000"]
    
    # Stripe Integration
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: Optional[str] = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Candidate Stripe Prices
    STRIPE_PRICE_CANDIDATE_PRO: str = "price_placeholder_candidate_pro"
    STRIPE_PRICE_CANDIDATE_PREMIUM: str = "price_placeholder_candidate_premium"
    
    # Company Stripe Prices
    STRIPE_PRICE_COMPANY_STARTUP: str = "price_placeholder_company_startup"
    STRIPE_PRICE_COMPANY_MSME: str = "price_placeholder_company_msme"
    STRIPE_PRICE_COMPANY_ENTERPRISE: str = "price_placeholder_company_enterprise"

    @property
    def candidate_stripe_prices(self) -> dict:
        return {
            "pro": self.STRIPE_PRICE_CANDIDATE_PRO,
            "premium": self.STRIPE_PRICE_CANDIDATE_PREMIUM,
        }

    @property
    def company_stripe_prices(self) -> dict:
        return {
            "startup": self.STRIPE_PRICE_COMPANY_STARTUP,
            "msme": self.STRIPE_PRICE_COMPANY_MSME,
            "enterprise": self.STRIPE_PRICE_COMPANY_ENTERPRISE,
        }
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
