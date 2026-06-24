from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class LinkedInProfileResponse(BaseModel):
    """Response for LinkedIn profile after OAuth completion."""
    user_id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    linkedin_id: str
    profile_picture: Optional[str] = None
    is_new_user: bool
    temporary_token: str
    expires_in: int

class LinkedInCompleteRegistration(BaseModel):
    """Complete registration after LinkedIn OAuth."""
    temporary_token: str
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    company_name: Optional[str] = Field(None, max_length=255, description="Company name (for employers)")
    company_website: Optional[str] = Field(None, max_length=500, description="Company website")
    role: Optional[str] = Field(None, description="Role: candidate or employer")
    additional_info: Optional[dict] = Field(None, description="Additional user information")

class LinkedInRegistrationComplete(BaseModel):
    """Response after completing registration."""
    user_id: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int

class LinkedInAuthRequest(BaseModel):
    """Request payload for LinkedIn OAuth callback from frontend."""
    code: str = Field(..., description="Authorization code from LinkedIn")
    redirectUri: str = Field(..., description="Frontend redirect URI used to request the code")
    role: Optional[str] = Field("candidate", description="User role (defaults to candidate)")

class AuthTokenDetails(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int

class AuthUser(BaseModel):
    id: str
    email: str
    fullName: str
    role: str
    onboardingCompleted: bool
    onboardingStep: int

class LinkedInAuthResponse(BaseModel):
    """Standard authentication response."""
    token: str
    tokens: AuthTokenDetails
    user: AuthUser
