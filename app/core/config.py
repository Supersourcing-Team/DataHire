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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 2
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
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "ayush@supersourcing.com"
    
    # CORS
    ALLOWED_ORIGINS: list = ["http://localhost:3000"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
