from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime

class EmailBaseModel(BaseModel):
    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def lowercase_email(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class RegisterRequest(EmailBaseModel):
    email: EmailStr
    full_name: str = Field(..., alias="fullName")
    role: str = Field(..., description="User role (candidate or employer)")

class LoginRequest(EmailBaseModel):
    email: EmailStr

class VerifyOTPRequest(EmailBaseModel):
    email: EmailStr
    otp_code: str = Field(..., alias="otpCode", min_length=6, max_length=10, description="The 6-digit OTP code")

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int

class CandidateProfile(BaseModel):
    user_id: str
    full_name: str
    phone: Optional[str] = None
    profile_picture: Optional[str] = None
    resume_url: Optional[str] = None
    resume_name: Optional[str] = None
    work_status_id: Optional[int] = None
    taxonomy_domain_id: Optional[int] = None
    visa_status_id: Optional[int] = None
    onboarding_step: int
    onboarding_completed: bool

class EmployerProfile(BaseModel):
    user_id: str
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_logo: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    organization_type_id: Optional[int] = None
    size_id: Optional[int] = None
    hiring_domains: List[int] = []
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    city_id: Optional[int] = None
    zipcode: Optional[str] = None
    industry_id: Optional[int] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    office_landline_number: Optional[str] = None
    alternate_email: Optional[str] = None
    work_mobile_number: Optional[str] = None
    onboarding_step: int
    onboarding_completed: bool

class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    onboarding_step: int = 0
    onboarding_completed: bool = False
    
    # We will include full onboarding data in the profile fields
    candidate_profile: Optional[CandidateProfile] = None
    employer_profile: Optional[EmployerProfile] = None
    plan_tier: Optional[str] = None
    
    @classmethod
    def from_orm(cls, user):
        onboarding_step = 0
        onboarding_completed = False
        
        candidate_data = None
        employer_data = None
        
        from app.services.s3_service import S3Service
        s3_service = S3Service()
        
        if user.role == "candidate" and user.candidate:
            onboarding_step = user.candidate.onboarding_step
            onboarding_completed = user.candidate.onboarding_completed
            
            # Find primary resume
            from app.models.resume import Resume
            primary_resume = next((r for r in user.candidate.resumes if r.is_primary), None) if hasattr(user.candidate, 'resumes') else None
            
            resume_url = primary_resume.file_url if primary_resume else None
            resume_name = primary_resume.file_name if primary_resume else None
            
            candidate_data = CandidateProfile(
                user_id=str(user.candidate.user_id),
                full_name=user.candidate.full_name,
                phone=user.candidate.phone,
                profile_picture=s3_service.get_presigned_url(user.candidate.profile_picture),
                resume_url=s3_service.get_presigned_url(resume_url),
                resume_name=resume_name,
                work_status_id=user.candidate.work_status_id,
                taxonomy_domain_id=user.candidate.taxonomy_domain_id,
                visa_status_id=user.candidate.visa_status_id,
                onboarding_step=user.candidate.onboarding_step,
                onboarding_completed=user.candidate.onboarding_completed
            )
        elif user.role == "employer" and user.employer:
            if user.employer.company:
                onboarding_step = user.employer.company.onboarding_step
                onboarding_completed = user.employer.company.onboarding_completed
                
                hiring_domain_ids = [d.id for d in user.employer.company.hiring_domains] if user.employer.company.hiring_domains else []
                
                employer_data = EmployerProfile(
                    user_id=str(user.employer.user_id),
                    company_name=user.employer.company.name,
                    company_website=user.employer.company.website,
                    company_logo=s3_service.get_presigned_url(user.employer.company.logo_url),
                    contact_person=user.employer.contact_person,
                    phone=user.employer.phone,
                    organization_type_id=user.employer.company.organization_type_id,
                    size_id=user.employer.company.size_id,
                    hiring_domains=hiring_domain_ids,
                    country_id=user.employer.company.country_id,
                    state_id=user.employer.company.state_id,
                    city_id=user.employer.company.city_id,
                    zipcode=user.employer.company.zipcode,
                    industry_id=user.employer.company.industry_id,
                    founded_year=user.employer.company.founded_year,
                    description=user.employer.company.description,
                    office_landline_number=user.employer.company.office_landline_number,
                    alternate_email=user.employer.company.alternate_email,
                    work_mobile_number=user.employer.company.work_mobile_number,
                    onboarding_step=user.employer.company.onboarding_step,
                    onboarding_completed=user.employer.company.onboarding_completed
                )
            else:
                employer_data = EmployerProfile(
                    user_id=str(user.employer.user_id),
                    contact_person=user.employer.contact_person,
                    phone=user.employer.phone,
                    onboarding_step=0,
                    onboarding_completed=False
                )

        plan_tier = user.candidate.plan_tier if (user.role == "candidate" and user.candidate) else None

        return cls(
            id=str(user.id),
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at,
            onboarding_step=onboarding_step,
            onboarding_completed=onboarding_completed,
            candidate_profile=candidate_data,
            employer_profile=employer_data,
            plan_tier=plan_tier
        )

class OTPRequest(EmailBaseModel):
    email: EmailStr
    purpose: str = Field(..., description="Purpose of OTP, e.g., 'ACCOUNT_VERIFICATION' or 'PASSWORD_RESET'")

class OTPVerify(EmailBaseModel):
    email: EmailStr
    otp_code: str = Field(..., min_length=6, max_length=10, description="The OTP code")
    purpose: str = Field(..., description="Purpose of OTP, e.g., 'ACCOUNT_VERIFICATION' or 'PASSWORD_RESET'")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., alias="refreshToken")

