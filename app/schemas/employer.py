from pydantic import BaseModel, AnyUrl
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class CompanyProfileResponse(BaseModel):
    id: UUID
    name: str
    website: Optional[str] = None
    logo_url: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    zipcode: Optional[str] = None
    office_landline_number: Optional[str] = None
    alternate_email: Optional[str] = None
    work_mobile_number: Optional[str] = None
    onboarding_step: int
    onboarding_completed: bool
    organization_type_id: Optional[int] = None
    industry_id: Optional[int] = None
    size_id: Optional[int] = None
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    city_id: Optional[int] = None
    custom_roles_hiring_for: Optional[str] = None

    class Config:
        from_attributes = True

class EmployerProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[CompanyProfileResponse] = None

    class Config:
        from_attributes = True

class EmployerProfileUpdate(BaseModel):
    # Employer fields
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    
    # Company fields
    company_name: Optional[str] = None
    company_website: Optional[AnyUrl] = None
    company_logo_url: Optional[str] = None
    company_founded_year: Optional[int] = None
    company_description: Optional[str] = None
    company_zipcode: Optional[str] = None
    company_office_landline: Optional[str] = None
    company_alternate_email: Optional[str] = None
    company_work_mobile: Optional[str] = None
    company_organization_type_id: Optional[int] = None
    company_industry_id: Optional[int] = None
    company_size_id: Optional[int] = None
    company_country_id: Optional[int] = None
    company_state_id: Optional[int] = None
    company_city_id: Optional[int] = None
    company_custom_roles: Optional[str] = None
