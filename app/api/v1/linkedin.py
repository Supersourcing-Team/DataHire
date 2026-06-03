from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.linkedin_oauth import LinkedInOAuthService
from app.services.auth_service import AuthService
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.core.config import settings
from app.schemas.auth_schemas import UserResponse, TokenResponse
from app.schemas.linkedin_schemas import LinkedInCompleteRegistration, LinkedInRegistrationComplete
from urllib.parse import urlencode, parse_qs
from datetime import datetime
import uuid

router = APIRouter(prefix="/auth/linkedin", tags=["linkedin-auth"])

@router.get("/login")
async def linkedin_login(redirect_url: str = None):
    """Redirect to LinkedIn OAuth login."""
    state = str(uuid.uuid4())
    
    # Include redirect_url in state parameter (simplified approach)
    if redirect_url:
        state = f"{state}:{redirect_url}"
    
    auth_url = LinkedInOAuthService.get_auth_url(state)
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def linkedin_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    db: Session = Depends(get_db)
):
    """Handle LinkedIn OAuth callback and redirect to frontend."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LinkedIn OAuth error: {error} - {error_description}"
        )
        
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code not found in request"
        )
        
    try:
        # Extract redirect_url from state if present
        redirect_url = None
        if state and ":" in state:
            parts = state.split(":", 1)
            state = parts[0]  # Original state
            redirect_url = parts[1] if len(parts) > 1 else None
        
        # Exchange code for tokens
        token_data = await LinkedInOAuthService.exchange_code_for_tokens(code)
        access_token = token_data['access_token']
        
        # Get user profile from LinkedIn
        profile_data = await LinkedInOAuthService.get_user_profile(access_token)
        
        # Create temporary user session
        temp_profile = await LinkedInOAuthService.create_temporary_user_session(db, profile_data)
        
        # For frontend integration, redirect to frontend with temporary token
        if redirect_url:
            # Redirect to frontend with temporary token
            frontend_url = f"{redirect_url}?temp_token={temp_profile.temporary_token}&is_new_user={temp_profile.is_new_user}"
            return RedirectResponse(url=frontend_url)
        else:
            # Return profile data for API testing
            return {
                "message": "LinkedIn authentication successful",
                "profile": temp_profile,
                "next_step": "Complete registration using the temporary token"
            }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LinkedIn authentication failed: {str(e)}"
        )

@router.post("/complete-registration")
async def complete_linkedin_registration(
    registration_data: LinkedInCompleteRegistration,
    db: Session = Depends(get_db)
):
    """Complete LinkedIn user registration with additional details."""
    try:
        result = await LinkedInOAuthService.complete_linkedin_registration(db, registration_data.dict())
        
        return {
            "message": "LinkedIn registration completed successfully",
            "user": result["user"],
            "tokens": result["tokens"]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration completion failed: {str(e)}"
        )

@router.get("/profile/{temp_token}")
async def get_temporary_profile(
    temp_token: str,
    db: Session = Depends(get_db)
):
    """Get user profile using temporary token."""
    try:
        # Verify temporary token
        payload = verify_token(temp_token)
        
        if not payload or payload.get("type") != "temporary":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired temporary token"
            )
        
        # Return profile information
        return {
            "message": "Temporary token valid",
            "profile": {
                "email": payload.get("email"),
                "first_name": payload.get("first_name"),
                "last_name": payload.get("last_name")
            },
            "next_step": "Complete registration with POST /auth/linkedin/complete-registration"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get profile: {str(e)}"
        )

@router.post("/token")
async def linkedin_token_exchange(
    code: str,
    db: Session = Depends(get_db)
):
    """Exchange LinkedIn authorization code for JWT tokens."""
    try:
        # Exchange code for tokens
        token_data = await LinkedInOAuthService.exchange_code_for_tokens(code)
        access_token = token_data['access_token']
        
        # Get user profile from LinkedIn
        profile_data = await LinkedInOAuthService.get_user_profile(access_token)
        
        # Create temporary user session
        temp_profile = await LinkedInOAuthService.create_temporary_user_session(db, profile_data)
        
        return {
            "message": "LinkedIn authentication successful",
            "profile": temp_profile,
            "next_step": "Complete registration using the temporary token"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token exchange failed: {str(e)}"
        )

@router.get("/url")
async def get_linkedin_auth_url():
    """Get LinkedIn OAuth authorization URL."""
    state = str(uuid.uuid4())
    auth_url = LinkedInOAuthService.get_auth_url(state)
    
    return {
        "authorization_url": auth_url,
        "state": state
    }
