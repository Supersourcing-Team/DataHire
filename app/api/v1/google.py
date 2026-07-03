from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.google_oauth import GoogleOAuthService
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.core.config import settings
from app.schemas.auth_schemas import UserResponse, TokenResponse
from app.schemas.google_schemas import GoogleCompleteRegistration, GoogleRegistrationComplete, GoogleAuthRequest, GoogleAuthResponse
from urllib.parse import urlencode, parse_qs
from datetime import datetime
import uuid

router = APIRouter(prefix="/auth/google", tags=["google-auth"])

@router.post("", response_model=GoogleAuthResponse)
async def authenticate_google(
    request: GoogleAuthRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Handle Google OAuth callback from frontend.
    Exchanges code for tokens, fetches profile, and returns app session.
    """
    try:
        result = await GoogleOAuthService.authenticate_with_google(
            db=db,
            code=request.code,
            redirect_uri=request.redirectUri,
            role=request.role
        )
        refresh_token = result["tokens"].pop("refresh_token", None)
        if refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=True,
                samesite=None,
                max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
                path="/"
            )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

@router.get("/login")
async def google_login(redirect_url: str = None):
    """Redirect to Google OAuth login."""
    state = str(uuid.uuid4())
    
    # Include redirect_url in state parameter (simplified approach)
    if redirect_url:
        state = f"{state}:{redirect_url}"
    
    auth_url = GoogleOAuthService.get_auth_url(state)
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def google_callback(
    code: str,
    state: str = None,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback and redirect to frontend."""
    try:
        # Extract redirect_url from state if present
        redirect_url = None
        if state and ":" in state:
            parts = state.split(":", 1)
            state = parts[0]  # Original state
            redirect_url = parts[1] if len(parts) > 1 else None
        
        # Exchange code for tokens
        token_data = await GoogleOAuthService.exchange_code_for_tokens(code)
        access_token = token_data['access_token']
        
        # Get user profile from Google
        profile_data = await GoogleOAuthService.get_user_profile(access_token)
        
        # Create temporary user session
        temp_profile = await GoogleOAuthService.create_temporary_user_session(db, profile_data)
        
        # For frontend integration, redirect to frontend with temporary token
        if redirect_url:
            frontend_url = f"{redirect_url}?temp_token={temp_profile.temporary_token}&is_new_user={temp_profile.is_new_user}"
            return RedirectResponse(url=frontend_url)
        else:
            # Return profile data for API testing
            return {
                "message": "Google authentication successful",
                "profile": temp_profile,
                "next_step": "Complete registration using the temporary token"
            }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authentication failed: {str(e)}"
        )

@router.post("/complete-registration")
async def complete_google_registration(
    registration_data: GoogleCompleteRegistration,
    response: Response,
    db: Session = Depends(get_db)
):
    """Complete Google user registration with additional details."""
    try:
        result = await GoogleOAuthService.complete_google_registration(db, registration_data.dict())
        refresh_token = result["tokens"].pop("refresh_token", None)
        if refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=True,
                samesite=None,
                max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
                path="/"
            )
        
        return {
            "message": "Google registration completed successfully",
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
                "last_name": payload.get("last_name"),
                "profile_picture": payload.get("profile_picture")
            },
            "next_step": "Complete registration with POST /auth/google/complete-registration"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get profile: {str(e)}"
        )

@router.get("/url")
async def get_google_auth_url():
    """Get Google OAuth authorization URL."""
    state = str(uuid.uuid4())
    auth_url = GoogleOAuthService.get_auth_url(state)
    
    return {
        "authorization_url": auth_url,
        "state": state
    }
