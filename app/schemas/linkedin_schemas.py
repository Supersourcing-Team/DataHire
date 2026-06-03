from pydantic import BaseModel, Field
from typing import Optional
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
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
