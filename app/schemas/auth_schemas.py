from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., alias="fullName")
    role: str = Field(..., description="User role (candidate or employer)")

class LoginRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., alias="otpCode", min_length=6, max_length=10, description="The 6-digit OTP code")

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int

class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_orm(cls, user):
        return cls(
            id=str(user.id),
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at
        )

class CandidateProfile(BaseModel):
    user_id: str
    full_name: str
    phone: Optional[str] = None
    profile_picture: Optional[str] = None
    onboarding_completed: bool

class EmployerProfile(BaseModel):
    user_id: str
    company_name: str
    company_website: Optional[str] = None
    company_logo: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    onboarding_completed: bool

class OTPRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(..., description="Purpose of OTP, e.g., 'ACCOUNT_VERIFICATION' or 'PASSWORD_RESET'")

class OTPVerify(BaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=10, description="The OTP code")
    purpose: str = Field(..., description="Purpose of OTP, e.g., 'ACCOUNT_VERIFICATION' or 'PASSWORD_RESET'")

