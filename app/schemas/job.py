from datetime import datetime
from typing import Optional
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
