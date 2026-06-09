from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class AdminCandidateResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_email: str
    full_name: str
    phone: Optional[str] = None
    profile_picture: Optional[str] = None
    onboarding_step: int
    onboarding_completed: bool
    work_status_id: Optional[int] = None
    work_status_name: Optional[str] = None
    taxonomy_domain_id: Optional[int] = None
    taxonomy_domain_name: Optional[str] = None
    visa_status_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminCompanyResponse(BaseModel):
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
    organization_type_name: Optional[str] = None
    industry_id: Optional[int] = None
    industry_name: Optional[str] = None
    size_id: Optional[int] = None
    size_label: Optional[str] = None
    country_id: Optional[int] = None
    country_name: Optional[str] = None
    state_id: Optional[int] = None
    state_name: Optional[str] = None
    city_id: Optional[int] = None
    city_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminJobResponse(BaseModel):
    id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    title: str
    description: str
    employment_type_id: Optional[int] = None
    employment_type_name: Optional[str] = None
    work_mode_id: Optional[int] = None
    work_mode_name: Optional[str] = None
    city_id: Optional[int] = None
    city_name: Optional[str] = None
    state_id: Optional[int] = None
    state_name: Optional[str] = None
    country_id: Optional[int] = None
    country_name: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency_id: Optional[int] = None
    currency_code: Optional[str] = None
    start_date: Optional[datetime] = None
    application_deadline: Optional[datetime] = None
    min_experience_years: int
    max_experience_years: Optional[int] = None
    requires_visa_sponsorship: bool
    num_positions: int
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserSuspensionResponse(BaseModel):
    message: str
    user_id: UUID
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

