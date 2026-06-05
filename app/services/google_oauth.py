import requests
from urllib.parse import urlencode
from app.core.config import settings
from app.schemas.auth_schemas import UserResponse
from app.schemas.google_schemas import GoogleProfileResponse
from app.models.user import User, UserRole, AuthProvider
from app.models.candidate import Candidate
from app.models.employer import Employer
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
from app.core.security import create_temporary_token, verify_token

class GoogleOAuthService:
    """Google OAuth2 integration service."""
    
    @staticmethod
    def get_auth_url(state: str = None) -> str:
        """Generate Google OAuth authorization URL."""
        params = {
            'response_type': 'code',
            'client_id': settings.GOOGLE_CLIENT_ID,
            'redirect_uri': settings.GOOGLE_REDIRECT_URI,
            'scope': 'openid email profile',
            'state': state or str(uuid.uuid4()),
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        base_url = 'https://accounts.google.com/o/oauth2/v2/auth'
        return f"{base_url}?{urlencode(params)}"
    
    @staticmethod
    async def exchange_code_for_tokens(code: str, redirect_uri: str = None) -> dict:
        """Exchange authorization code for access tokens."""
        token_url = 'https://oauth2.googleapis.com/token'
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri or settings.GOOGLE_REDIRECT_URI,
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET
        }
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        return response.json()
    
    @staticmethod
    async def get_user_profile(access_token: str) -> dict:
        """Get user profile from Google API."""
        profile_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        profile_response = requests.get(profile_url, headers=headers)
        profile_response.raise_for_status()
        profile_data = profile_response.json()
        
        user_info = {
            'google_id': profile_data.get('id'),
            'first_name': profile_data.get('given_name', ''),
            'last_name': profile_data.get('family_name', ''),
            'email': profile_data.get('email', ''),
            'profile_picture': profile_data.get('picture', '')
        }
        
        return user_info
    
    @staticmethod
    async def create_temporary_user_session(db: Session, profile_data: dict) -> GoogleProfileResponse:
        """Create temporary user session after Google OAuth."""
        email = profile_data['email']
        google_id = profile_data['google_id']
        first_name = profile_data['first_name']
        last_name = profile_data['last_name']
        profile_picture = profile_data.get('profile_picture')
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        is_new_user = existing_user is None
        
        if existing_user and existing_user.auth_provider != AuthProvider.GOOGLE:
            # Optionally link account or reject. Here we mimic LinkedIn and reject if provider mismatch.
            raise ValueError(f"Email already registered with different authentication method ({existing_user.auth_provider})")
        
        # Generate temporary JWT for frontend completion
        temp_token_data = {
            "email": email,
            "google_id": google_id,
            "first_name": first_name,
            "last_name": last_name,
            "profile_picture": profile_picture
        }
        
        temp_token = create_temporary_token(temp_token_data)
        full_name = f"{first_name} {last_name}".strip()
        
        return GoogleProfileResponse(
            user_id=str(existing_user.id) if existing_user else None,
            email=email,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            google_id=google_id,
            profile_picture=profile_picture,
            is_new_user=is_new_user,
            temporary_token=temp_token,
            expires_in=900  # 15 minutes
        )
    
    @staticmethod
    async def complete_google_registration(db: Session, registration_data: dict) -> dict:
        """Complete Google user registration with additional details."""
        temp_token = registration_data['temporary_token']
        role = registration_data['role']
        
        # Verify temporary token
        payload = verify_token(temp_token)
        
        if not payload or payload.get("type") != "temporary":
            raise ValueError("Invalid or expired temporary token")
        
        # Extract trusted details from the JWT
        email = payload.get('email')
        google_id = payload.get('google_id')
        first_name = payload.get('first_name', '')
        last_name = payload.get('last_name', '')
        profile_picture = payload.get('profile_picture')
        
        if not email:
            raise ValueError("Invalid token payload: missing email")
        
        # Check if user already exists
        user = db.query(User).filter(User.email == email).first()
        
        if user:
            # Update existing user
            user.last_login = datetime.utcnow()
            user.updated_at = datetime.utcnow()
            if not user.profile_picture and profile_picture:
                user.profile_picture = profile_picture
                
            # Update role-specific profile
            if role == UserRole.CANDIDATE and user.candidate:
                candidate = user.candidate
                candidate.phone = registration_data.get('phone')
                candidate.updated_at = datetime.utcnow()
            elif role == UserRole.EMPLOYER and user.employer:
                employer = user.employer
                employer.company_name = registration_data.get('company_name')
                employer.company_website = registration_data.get('company_website')
                employer.phone = registration_data.get('phone')
                employer.updated_at = datetime.utcnow()
        else:
            # Create new user based on Google profile data from token
            user = User(
                email=email,
                google_id=google_id,
                profile_picture=profile_picture,
                password_hash=None,
                role=role,
                auth_provider=AuthProvider.GOOGLE,
                is_active=True,
                is_verified=True,  # Google emails are verified
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Use full name from frontend payload if available, else from JWT
            full_name = registration_data.get('full_name')
            if not full_name:
                full_name = f"{first_name} {last_name}".strip()
            
            # Create role-specific profile
            if role == UserRole.CANDIDATE:
                candidate = Candidate(
                    user_id=user.id,
                    full_name=full_name,
                    phone=registration_data.get('phone'),
                    onboarding_completed=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(candidate)
            elif role == UserRole.EMPLOYER:
                employer = Employer(
                    user_id=user.id,
                    company_name=registration_data.get('company_name', ''),
                    company_website=registration_data.get('company_website'),
                    contact_person=full_name,
                    phone=registration_data.get('phone'),
                    onboarding_completed=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(employer)
            
            db.commit()
        
        # Generate final JWT tokens
        from app.core.security import create_access_token, create_refresh_token
        from app.core.config import settings
        
        access_token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "provider": "google"
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

    @staticmethod
    async def authenticate_with_google(db: Session, code: str, redirect_uri: str, role: str = "candidate") -> dict:
        """Authenticate user with Google authorization code."""
        try:
            # Exchange code for tokens using dynamic redirect URI
            token_data = await GoogleOAuthService.exchange_code_for_tokens(code, redirect_uri)
            access_token = token_data['access_token']
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code >= 400 and e.response.status_code < 500:
                raise ValueError("Failed to exchange authorization code: Code has expired or is invalid.")
            raise ConnectionError("External authentication provider is temporarily unavailable.")
            
        try:
            # Get user profile from Google
            profile_data = await GoogleOAuthService.get_user_profile(access_token)
        except requests.exceptions.RequestException:
            raise ConnectionError("External authentication provider is temporarily unavailable.")
            
        email = profile_data.get('email')
        google_id = profile_data.get('google_id')
        first_name = profile_data.get('first_name', '')
        last_name = profile_data.get('last_name', '')
        full_name = f"{first_name} {last_name}".strip()
        profile_picture = profile_data.get('profile_picture')
        
        # Check if user already exists
        user = db.query(User).filter(User.email == email).first()
        
        if user:
            # Update last login
            user.last_login = datetime.utcnow()
            user.updated_at = datetime.utcnow()
            if not user.profile_picture and profile_picture:
                user.profile_picture = profile_picture
            
            # Fetch onboarding status based on role
            onboarding_completed = False
            onboarding_step = 0
            
            if user.role == UserRole.CANDIDATE and user.candidate:
                onboarding_completed = user.candidate.onboarding_completed
                onboarding_step = user.candidate.onboarding_step
            elif user.role == UserRole.EMPLOYER and user.employer:
                onboarding_completed = getattr(user.employer, 'onboarding_completed', True)
                onboarding_step = getattr(user.employer, 'onboarding_step', 0)
        else:
            # Create new user
            user = User(
                email=email,
                google_id=google_id,
                password_hash=None,
                role=role,
                auth_provider=AuthProvider.GOOGLE,
                is_active=True,
                is_verified=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                profile_picture=profile_picture
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            onboarding_completed = False
            onboarding_step = 0
            
            # Create role-specific profile
            if role == UserRole.CANDIDATE:
                candidate = Candidate(
                    user_id=user.id,
                    full_name=full_name,
                    onboarding_completed=False,
                    onboarding_step=0,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    profile_picture=profile_picture
                )
                db.add(candidate)
            elif role == UserRole.EMPLOYER:
                employer = Employer(
                    user_id=user.id,
                    contact_person=full_name,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(employer)
                
            db.commit()
            db.refresh(user)
            
        # Generate final JWT tokens
        from app.core.security import create_access_token, create_refresh_token
        from app.core.config import settings
        
        access_token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "provider": "google"
        }
        
        app_access_token = create_access_token(access_token_data)
        app_refresh_token = create_refresh_token({"sub": str(user.id)})
        
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        
        return {
            "token": app_access_token,
            "tokens": {
                "access_token": app_access_token,
                "refresh_token": app_refresh_token,
                "token_type": "Bearer",
                "expires_in": expires_in
            },
            "user": {
                "id": str(user.id),
                "email": user.email,
                "fullName": full_name,
                "role": user.role,
                "onboardingCompleted": onboarding_completed,
                "onboardingStep": onboarding_step
            }
        }
