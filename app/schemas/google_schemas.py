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

class GoogleAuthRequest(BaseModel):
    """Request payload for Google OAuth callback from frontend."""
    code: str = Field(..., description="Authorization code from Google")
    redirectUri: str = Field(..., description="Frontend redirect URI used to request the code")
    role: Optional[str] = Field("candidate", description="User role (defaults to candidate)")

class AuthTokenDetails(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

class AuthUser(BaseModel):
    id: str
    email: str
    fullName: str
    role: str
    onboardingCompleted: bool
    onboardingStep: int

class GoogleAuthResponse(BaseModel):
    """Standard authentication response."""
    token: str
    tokens: AuthTokenDetails
    user: AuthUser
