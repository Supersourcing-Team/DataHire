from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class GoogleProfileResponse(BaseModel):
    """Schema for returning Google profile data and temporary token."""
    user_id: Optional[str] = None
    email: EmailStr
    first_name: str
    last_name: str
    full_name: str
    google_id: str
    profile_picture: Optional[str] = None
    is_new_user: bool
    temporary_token: str
    expires_in: int

class GoogleCompleteRegistration(BaseModel):
    """Schema for completing registration after Google authentication."""
    temporary_token: str = Field(..., description="The temporary JWT received from Google OAuth callback")
    role: str = Field(..., description="User role (candidate or employer)")
    
    # Candidate specific fields
    phone: Optional[str] = None
    full_name: Optional[str] = None
    
    # Employer specific fields
    company_name: Optional[str] = None
    company_website: Optional[str] = None

class GoogleRegistrationComplete(BaseModel):
    """Response schema after completing Google registration."""
    message: str
    user: dict
    tokens: dict
