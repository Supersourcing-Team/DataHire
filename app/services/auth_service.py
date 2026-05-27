from sqlalchemy.orm import Session
from app.models.user import User, UserRole, AuthProvider
from app.models.candidate import Candidate
from app.models.employer import Employer
from app.schemas.auth_schemas import UserResponse, RegisterRequest
from app.core.security import create_access_token, create_refresh_token
from app.core.config import settings
from datetime import datetime

class AuthService:
    @staticmethod
    async def register_user(db: Session, registration_data: RegisterRequest) -> dict:
        """Register a new user directly."""
        email = registration_data.email
        role = registration_data.role
        full_name = registration_data.full_name
        
        # Check if user already exists
        user = db.query(User).filter(User.email == email).first()
        
        if user:
            raise ValueError("User already exists with this email")
            
        # Create new user
        user = User(
            email=email,
            password_hash=None, # Passwordless!
            role=role,
            auth_provider=AuthProvider.LOCAL,
            is_active=True,
            is_verified=False, # Must verify OTP first
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Create role-specific profile
        if role == UserRole.CANDIDATE:
            candidate = Candidate(
                user_id=user.id,
                full_name=full_name,
                onboarding_completed=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(candidate)
        elif role == UserRole.EMPLOYER:
            # For employer, we use contact_person as full_name initially, 
            # and leave company_name blank until they provide it.
            employer = Employer(
                user_id=user.id,
                contact_person=full_name,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(employer)
            
        db.commit()
        return {"message": "User registered successfully"}
        
    @staticmethod
    async def generate_tokens(db: Session, user: User) -> dict:
        """Generate tokens for a user who just verified their OTP."""
        # Update last login timestamp
        user.last_login = datetime.utcnow()
        db.commit()
        
        access_token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "provider": user.auth_provider
        }
        
        access_token = create_access_token(access_token_data)
        refresh_token = create_refresh_token({"sub": str(user.id)})
        
        return {
            "user": UserResponse.from_orm(user),
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            }
        }
