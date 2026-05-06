from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72, description="Password (max 72 characters)")

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72, description="Password (8-72 characters)")
    full_name: Optional[str] = None
    role: Optional[str] = None

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
