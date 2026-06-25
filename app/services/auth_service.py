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
            if user.is_verified:
                raise ValueError("User already exists with this email")
            
            # User exists but never verified the OTP (e.g., dropped off, network timeout)
            # Re-use the user record, update their role, and update the role-specific profile
            user.role = role
            user.updated_at = datetime.utcnow()
            
            if role == UserRole.CANDIDATE:
                # Clean up employer profile if it exists
                if user.employer:
                    db.delete(user.employer)
                
                # Create or update candidate profile
                if user.candidate:
                    user.candidate.full_name = full_name
                    user.candidate.updated_at = datetime.utcnow()
                else:
                    candidate = Candidate(
                        user_id=user.id,
                        full_name=full_name,
                        onboarding_completed=False,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(candidate)
            elif role == UserRole.EMPLOYER:
                # Clean up candidate profile if it exists
                if user.candidate:
                    db.delete(user.candidate)
                
                # Create or update employer profile
                if user.employer:
                    user.employer.contact_person = full_name
                    user.employer.updated_at = datetime.utcnow()
                else:
                    employer = Employer(
                        user_id=user.id,
                        contact_person=full_name,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(employer)
            
            db.commit()
            db.refresh(user)
        else:
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
