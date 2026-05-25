import requests
from urllib.parse import urlencode
from app.core.config import settings
from app.schemas.auth_schemas import UserResponse
from app.schemas.linkedin_schemas import LinkedInProfileResponse
from app.models.user import User, UserRole, AuthProvider
from app.models.candidate import Candidate
from app.models.employer import Employer
from app.models.refresh_token import RefreshToken
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
from app.core.security import create_temporary_token, verify_token

class LinkedInOAuthService:
    """LinkedIn OAuth2 integration service."""
    
    @staticmethod
    def get_auth_url(state: str = None) -> str:
        """Generate LinkedIn OAuth authorization URL."""
        params = {
            'response_type': 'code',
            'client_id': settings.LINKEDIN_CLIENT_ID,
            'redirect_uri': settings.LINKEDIN_REDIRECT_URI,
            'scope': 'openid profile email',  # Modern OpenID Connect scopes
            'state': state or str(uuid.uuid4())
        }
        
        base_url = 'https://www.linkedin.com/oauth/v2/authorization'
        return f"{base_url}?{urlencode(params)}"
    
    @staticmethod
    async def exchange_code_for_tokens(code: str) -> dict:
        """Exchange authorization code for access tokens."""
        token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.LINKEDIN_REDIRECT_URI,
            'client_id': settings.LINKEDIN_CLIENT_ID,
            'client_secret': settings.LINKEDIN_CLIENT_SECRET
        }
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        return response.json()
    
    @staticmethod
    async def get_user_profile(access_token: str) -> dict:
        """Get user profile from LinkedIn API using OpenID Connect."""
        profile_url = 'https://api.linkedin.com/v2/userinfo'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Connection': 'Keep-Alive'
        }
        
        profile_response = requests.get(profile_url, headers=headers)
        profile_response.raise_for_status()
        profile_data = profile_response.json()
        
        # Extract user information based on OIDC standard claims
        user_info = {
            'linkedin_id': profile_data.get('sub'),
            'first_name': profile_data.get('given_name', ''),
            'last_name': profile_data.get('family_name', ''),
            'email': profile_data.get('email', ''),
            'profile_picture': profile_data.get('picture', '')
        }
        
        return user_info
    
    @staticmethod
    async def create_temporary_user_session(db: Session, profile_data: dict) -> LinkedInProfileResponse:
        """Create temporary user session after LinkedIn OAuth."""
        email = profile_data['email']
        linkedin_id = profile_data['linkedin_id']
        first_name = profile_data['first_name']
        last_name = profile_data['last_name']
        
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        is_new_user = existing_user is None
        
        if existing_user and existing_user.auth_provider != AuthProvider.LINKEDIN:
            raise ValueError("Email already registered with different authentication method")
        
        # Generate temporary JWT for frontend completion
        temp_token_data = {
            "email": email,
            "linkedin_id": linkedin_id,
            "first_name": first_name,
            "last_name": last_name
        }
        
        temp_token = create_temporary_token(temp_token_data)
        
        full_name = f"{first_name} {last_name}".strip()
        
        return LinkedInProfileResponse(
            user_id=str(existing_user.id) if existing_user else None,
            email=email,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            linkedin_id=linkedin_id,
            profile_picture=profile_data.get('profile_picture'),
            is_new_user=is_new_user,
            temporary_token=temp_token,
            expires_in=900  # 15 minutes
        )
    
    @staticmethod
    async def complete_linkedin_registration(db: Session, registration_data: dict) -> dict:
        """Complete LinkedIn user registration with additional details."""
        temp_token = registration_data['temporary_token']
        role = registration_data['role']
        
        # Verify temporary token
        payload = verify_token(temp_token)
        
        if not payload or payload.get("type") != "temporary":
            raise ValueError("Invalid or expired temporary token")
        
        # Extract trusted details from the JWT
        email = payload.get('email')
        linkedin_id = payload.get('linkedin_id')
        first_name = payload.get('first_name', '')
        last_name = payload.get('last_name', '')
        
        if not email:
            raise ValueError("Invalid token payload: missing email")
        
        # Check if user already exists
        user = db.query(User).filter(User.email == email).first()
        
        if user:
            # Update existing user
            user.last_login = datetime.utcnow()
            user.updated_at = datetime.utcnow()
            
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
            # Create new user based on LinkedIn profile data from token
            user = User(
                email=email,
                linkedin_id=linkedin_id,
                password_hash=None,
                role=role,
                auth_provider=AuthProvider.LINKEDIN,
                is_active=True,
                is_verified=True,
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
            "provider": "linkedin"
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
