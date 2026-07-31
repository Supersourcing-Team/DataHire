from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie
from typing import Optional
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth_schemas import UserResponse, RegisterRequest, LoginRequest, VerifyOTPRequest, TokenResponse, RefreshTokenRequest
from app.services.auth_service import AuthService
from app.services.otp_service import OTPService
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.core.security import verify_token, create_access_token, create_refresh_token
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile."""
    return UserResponse.from_orm(current_user)

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """Register a new user and send verification OTP."""
    try:
        # Create the user and their specific profile
        await AuthService.register_user(db, request)
        
        # Automatically trigger an OTP email
        success = await OTPService.request_otp(db, request.email, "LOGIN_OR_SIGNUP")
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User registered, but failed to send OTP email. Please try logging in to trigger a new OTP."
            )
            
        return {"message": "User registered successfully. Please check your email for the OTP."}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/login", status_code=status.HTTP_200_OK)
async def request_login_otp(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """Generate and send a login OTP code to the provided email."""
    # Check if user exists
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )
        
    success = await OTPService.request_otp(db, request.email, "LOGIN_OR_SIGNUP")
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP email. Please try again later."
        )
    return {"message": "OTP sent successfully"}

@router.post("/otp/send", status_code=status.HTTP_200_OK)
async def resend_otp(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """Resend OTP code to the provided email with a 60-second cooldown."""
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )
        
    if not OTPService.can_request_otp(db, request.email, "LOGIN_OR_SIGNUP", cooldown_seconds=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting a new OTP."
        )
        
    success = await OTPService.request_otp(db, request.email, "LOGIN_OR_SIGNUP")
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend OTP email. Please try again later."
        )
    return {"message": "OTP resent successfully"}

@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def verify_login_otp(
    request: VerifyOTPRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Verify login OTP and return JWT tokens."""
    is_valid = await OTPService.verify_otp(db, request.email, request.otp_code, "LOGIN_OR_SIGNUP")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check your OTP and try again."
        )
        
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account has been deactivated. Please contact support."
        )
        
    # If this was their first time verifying (i.e. right after registration), mark as verified
    if not user.is_verified:
        user.is_verified = True
        db.commit()
        
    # Generate and return permanent tokens
    result = await AuthService.generate_tokens(db, user)
    
    # Store refresh token in HttpOnly Secure cookie
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
        "message": "Login successful",
        "user": result["user"],
        "tokens": result["tokens"]
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    response: Response,
    request: Optional[RefreshTokenRequest] = None,
    refresh_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
) -> TokenResponse:
    """
    Refresh the access token using a valid refresh token.
    """
    token_val = refresh_token
    if not token_val and request:
        token_val = request.refresh_token
        
    if not token_val:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = verify_token(token_val)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_440_LOGIN_TIMEOUT if hasattr(status, 'HTTP_440_LOGIN_TIMEOUT') else status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
        
    # Generate new access token
    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "provider": user.auth_provider
    }
    access_token = create_access_token(access_token_data)
    
    # Rotate refresh token
    new_refresh_token = create_refresh_token({"sub": str(user.id)})
    
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite=None,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/"
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=None,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

