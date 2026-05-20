from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth_schemas import UserLogin, UserRegister, TokenResponse, UserResponse, OTPRequest, OTPVerify, ForgotPasswordRequest, ResetPasswordRequest
from app.services.auth_service import AuthService, pwd_context
from app.services.otp_service import OTPService
from app.core.dependencies import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: Session = Depends(get_db)
):
    """Register a new user."""
    try:
        user = await AuthService.register_user(db, user_data)
        return UserResponse.from_orm(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/login", response_model=TokenResponse)
async def login(
    user_data: UserLogin,
    db: Session = Depends(get_db)
):
    """Authenticate user and return tokens."""
    try:
        tokens = await AuthService.authenticate_user(db, user_data.email, user_data.password)
        return TokenResponse(**tokens)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile."""
    return UserResponse.from_orm(current_user)

@router.post("/otp/send", status_code=status.HTTP_200_OK)
async def send_otp(
    request: OTPRequest,
    db: Session = Depends(get_db)
):
    """Generate and send an OTP code to the provided email."""
    success = await OTPService.request_otp(db, request.email, request.purpose)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP email. Please try again later."
        )
    return {"message": "OTP sent successfully"}

@router.post("/otp/verify", status_code=status.HTTP_200_OK)
async def verify_otp(
    request: OTPVerify,
    db: Session = Depends(get_db)
):
    """Verify an OTP code."""
    is_valid = await OTPService.verify_otp(db, request.email, request.otp_code, request.purpose)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code"
        )
        
    # If the purpose is account verification, update the user status
    if request.purpose == "ACCOUNT_VERIFICATION":
        user = db.query(User).filter(User.email == request.email).first()
        if user and not user.is_verified:
            user.is_verified = True
            db.commit()
            
    return {"message": "OTP verified successfully"}

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """Request a password reset OTP."""
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        # We only send OTP if the user exists, but we always return success to prevent email enumeration
        await OTPService.request_otp(db, request.email, "PASSWORD_RESET")
        
    return {"message": "If that email is registered, you will receive a password reset OTP shortly."}

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """Reset the password using an OTP."""
    is_valid = await OTPService.verify_otp(db, request.email, request.otp_code, "PASSWORD_RESET")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code"
        )
        
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    # Hash and update password
    password = request.new_password[:72]
    user.password_hash = pwd_context.hash(password)
    db.commit()
            
    return {"message": "Password reset successfully"}
