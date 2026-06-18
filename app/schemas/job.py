from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobDashboardCardResponse(BaseModel):
    id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    company_verified: Optional[bool] = None
    job_title: str
    ai_score: Optional[int] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    location_label: Optional[str] = None
    work_mode: Optional[str] = None
    sponsorship_label: Optional[str] = None
    posted_at: datetime
    posted_ago: Optional[str] = None
    experience_min_years: Optional[int] = None
    experience_max_years: Optional[int] = None
    experience_label: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency_code: Optional[str] = None
    salary_currency_symbol: Optional[str] = None
    salary_range_label: Optional[str] = None
    employment_type: Optional[str] = None
    save_action: Optional[str] = None
    apply_action: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobCreate(BaseModel):
    title: str
    description: Optional[str] = None
    employment_type_id: Optional[int] = None
    work_mode_id: Optional[int] = None
    city_id: Optional[int] = None
    state_id: Optional[int] = None
    country_id: Optional[int] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency_id: Optional[int] = None
    start_date: Optional[datetime] = None
    application_deadline: Optional[datetime] = None
    min_experience_years: Optional[int] = 0
    max_experience_years: Optional[int] = None
    requires_visa_sponsorship: Optional[bool] = False
    num_positions: Optional[int] = 1
    status: Optional[str] = "draft"
    is_active: Optional[bool] = True

    # New job flow fields
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    include_cover_letter: Optional[bool] = False
    cover_letter_required: Optional[bool] = False


class JobResponse(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    description: Optional[str] = None
    employment_type_id: Optional[int] = None
    work_mode_id: Optional[int] = None
    city_id: Optional[int] = None
    state_id: Optional[int] = None
    country_id: Optional[int] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency_id: Optional[int] = None
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

    # New job flow fields
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    include_cover_letter: bool
    cover_letter_required: bool

    model_config = ConfigDict(from_attributes=True)

