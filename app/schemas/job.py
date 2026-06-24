from datetime import datetime
from typing import List, Optional, Literal
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
    # state_id: Optional[int] = None
    # country_id: Optional[int] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency_id: Optional[int] = None
    start_date: Optional[datetime] = None
    application_deadline: Optional[datetime] = None
    min_experience_years: int
    max_experience_years: Optional[int] = None
    requires_visa_sponsorship: Optional[int] = None
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


class JobCreateBasic(BaseModel):
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
    application_deadline: Optional[int] = None
    min_experience_years: Optional[int] = 0
    max_experience_years: Optional[int] = None
    requires_visa_sponsorship: Optional[bool] = False
    num_positions: Optional[int] = 1


class JobAboutUpdate(BaseModel):
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None


class JobWorkAuthorizationUpdate(BaseModel):
    must_be_authorized_to_work: Optional[bool] = None
    requires_visa_sponsorship: Optional[bool] = None
    us_citizen_or_pr_only: Optional[bool] = None
    security_clearance_required: Optional[bool] = None
    ai_score_threshold: Optional[int] = None


class JobCoverLetterUpdate(BaseModel):
    include_cover_letter: Optional[bool] = None
    cover_letter_required: Optional[bool] = None


class JobPublishUpdate(BaseModel):
    status: Literal["draft", "published"]


class JobPosterDashboardKPIs(BaseModel):
    total_jobs: int
    total_applicants: int
    total_interviews: int
    total_hired: int


class MonthlySuccessRatePoint(BaseModel):
    month: str
    rate: float


class HiresByDomainPoint(BaseModel):
    domain: str
    count: int


class ActionFeedItem(BaseModel):
    id: str
    type: str
    title: str
    description: str
    created_at: datetime


class FunnelStagePoint(BaseModel):
    stage: str
    count: int


class JobStatusBreakdown(BaseModel):
    active_posts: int
    draft_posts: int
    closed_posts: int
    total_visitors: int


class JobPosterDashboardResponse(BaseModel):
    kpis: JobPosterDashboardKPIs
    monthly_success_rate: List[MonthlySuccessRatePoint]
    hires_by_domain: List[HiresByDomainPoint]
    action_feed: List[ActionFeedItem]
    hiring_funnel: List[FunnelStagePoint]
    job_status_overview: JobStatusBreakdown


class EmployerJobListingItem(BaseModel):
    id: UUID
    company_name: str
    company_logo_url: Optional[str] = None
    company_verified: bool = True
    job_title: str
    ai_score_threshold: int
    work_modes_list: List[str]
    visa_sponsorships_list: List[str]
    location_label: Optional[str] = None
    posted_ago: str
    new_applicants_count: int
    shortlisted_count: int
    deadline_label: Optional[str] = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class PipelineStageSummary(BaseModel):
    applied: int
    shortlisted: int
    interview: int
    onhold: int
    hired: int
    rejected: int

    model_config = ConfigDict(from_attributes=True)


class EmployerCompanyDetails(BaseModel):
    name: str
    website: Optional[str] = None
    logo_url: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    location: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EmployerJobDetailResponse(BaseModel):
    id: UUID
    company_name: str
    company_logo_url: Optional[str] = None
    company_verified: bool = True
    job_title: str
    ai_score_threshold: int
    work_modes_list: List[str]
    visa_sponsorships_list: List[str]
    location_label: Optional[str] = None
    posted_ago: str
    new_applicants_count: int
    shortlisted_count: int
    deadline_label: Optional[str] = None
    status: str
    pipeline_summary: PipelineStageSummary
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    company_details: EmployerCompanyDetails

    model_config = ConfigDict(from_attributes=True)


class JobPosterApplicantListItem(BaseModel):
    id: UUID
    full_name: str
    profile_picture: Optional[str] = None
    is_verified: bool
    role: Optional[str] = None
    ai_score: int
    experience_years: int
    salary_range_label: Optional[str] = None
    employment_type: Optional[str] = None
    status: str
    applied_date: datetime

    model_config = ConfigDict(from_attributes=True)


class TimelineEvent(BaseModel):
    title: str
    status: str  # "completed", "active", "pending"
    updated_at: Optional[datetime] = None


class JobPosterApplicantProfileResponse(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    profile_picture: Optional[str] = None
    is_verified: bool
    role: Optional[str] = None
    ai_score: int
    experience_years: int
    salary_range_label: Optional[str] = None
    employment_type: Optional[str] = None
    preferred_location: Optional[str] = None
    status: str
    about_summary: Optional[str] = None
    resume_file_name: Optional[str] = None
    resume_file_url: Optional[str] = None
    cover_letter: Optional[str] = None
    timeline: List[TimelineEvent]

    model_config = ConfigDict(from_attributes=True)






