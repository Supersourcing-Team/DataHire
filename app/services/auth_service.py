from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.models.user import User, UserRole
from app.models.candidate import Candidate
from app.models.employer import Employer
from app.schemas.auth_schemas import UserRegister
from app.core.security import create_access_token, create_refresh_token
from app.core.config import settings
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    @staticmethod
    async def register_user(db: Session, user_data: UserRegister) -> User:
        """Register a new user."""
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise ValueError("Email already registered")
        
        # Truncate password to 72 bytes for bcrypt compatibility
        password = user_data.password[:72]
        
        # Hash password
        password_hash = pwd_context.hash(password)
        
        # Create user
        
        user = User(
            email=user_data.email,
            password_hash=password_hash,
            role=user_data.role or UserRole.CANDIDATE,
            auth_provider="local",
            is_active=True,
            is_verified=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Create role-specific profile
        if user.role == UserRole.CANDIDATE:
            candidate = Candidate(
                user_id=user.id,
                full_name=user_data.full_name or "",
                onboarding_completed=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(candidate)
        elif user.role == UserRole.EMPLOYER:
            employer = Employer(
                user_id=user.id,
                company_name=user_data.full_name or "",
                onboarding_completed=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(employer)
        
        db.commit()
        return user
    
    @staticmethod
    async def authenticate_user(db: Session, email: str, password: str) -> dict:
        """Authenticate user and return tokens."""
        user = db.query(User).filter(User.email == email).first()
        
        # Truncate password to 72 bytes for bcrypt compatibility
        password = password[:72]
        
        if not user or not pwd_context.verify(password, user.password_hash):
            raise ValueError("Invalid email or password")
        
        # Generate JWT tokens
        access_token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role
        }
        
        access_token = create_access_token(access_token_data)
        refresh_token = create_refresh_token({"sub": str(user.id)})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
        }
