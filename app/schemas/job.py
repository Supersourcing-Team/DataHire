from datetime import datetime
from typing import List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, Field

from app.schemas.taxonomy import TaxonomyJobRoleResponse
from app.schemas.meta import (
    MetaEmploymentTypeResponse,
    MetaWorkModeResponse,
    MetaCityResponse,
    MetaStateResponse,
    MetaCountryResponse,
    MetaCurrencyResponse,
    MetaVisaStatusResponse
)


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
    requires_visa_sponsorship: Optional[int] = None
    visa_sponsorship_ids: Optional[List[int]] = None
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
    employment_type: Optional[MetaEmploymentTypeResponse] = None
    work_mode_id: Optional[int] = None
    work_mode: Optional[MetaWorkModeResponse] = None
    city_id: Optional[int] = None
    city: Optional[MetaCityResponse] = None
    state_id: Optional[int] = None
    state: Optional[MetaStateResponse] = None
    country_id: Optional[int] = None
    country: Optional[MetaCountryResponse] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency_id: Optional[int] = None
    currency: Optional[MetaCurrencyResponse] = None
    start_date: Optional[datetime] = None
    application_deadline: Optional[datetime] = None
    min_experience_years: int
    max_experience_years: Optional[int] = None
    requires_visa_sponsorship: Optional[int] = None
    visa_status: Optional[MetaVisaStatusResponse] = None
    visa_sponsorship_ids: Optional[List[int]] = None
    visa_statuses: Optional[List[MetaVisaStatusResponse]] = None
    taxonomy_job_role_id: Optional[int] = None
    taxonomy_job_role: Optional[TaxonomyJobRoleResponse] = None
    num_positions: int
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    ai_score_threshold: Optional[int] = None
    must_be_authorized_to_work: Optional[bool] = None
    us_citizen_or_pr_only: Optional[bool] = None
    security_clearance_required: Optional[bool] = None
    # New job flow fields
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    include_cover_letter: bool
    cover_letter_required: bool
    is_valid: bool = False

    model_config = ConfigDict(from_attributes=True)

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def convert_monthly_to_yearly(cls, v):
        if v is not None:
            return v 
        return v


class JobCreateBasic(BaseModel):
    title: str
    description: Optional[str] = None
    employment_type_id: Optional[int] = None
    work_mode_id: Optional[int] = None
    city_id: Optional[int] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency_id: Optional[int] = None
    application_deadline: Optional[int] = None
    min_experience_years: Optional[int] = 0
    max_experience_years: Optional[int] = None
    requires_visa_sponsorship: Optional[int] = None
    visa_sponsorship_ids: Optional[List[int]] = None
    num_positions: Optional[int] = 1


class JobAboutUpdate(BaseModel):
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None


class JobWorkAuthorizationUpdate(BaseModel):
    must_be_authorized_to_work: Optional[bool] = None
    requires_visa_sponsorship: Optional[int] = None
    visa_sponsorship_ids: Optional[List[int]] = None
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
    status_label: str
    is_valid: bool = False

    model_config = ConfigDict(from_attributes=True)


class PipelineStageSummary(BaseModel):
    applied: int
    shortlisted: int
    interview: int
    onhold: int
    hired: int
    rejected: int

    model_config = ConfigDict(from_attributes=True)


class JobCandidateStatsResponse(BaseModel):
    application: int
    shortlisted: int
    interview: int
    hired: int
    onhold: int
    reject: int

    model_config = ConfigDict(from_attributes=True)


class EmployerCompanyDetails(BaseModel):
    name: str
    website: Optional[str] = None
    logo_url: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    location: Optional[str] = None
    company_size: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class EmployerJobDetailResponse(BaseModel):
    id: UUID
    company_name: str
    company_logo_url: Optional[str] = None
    company_verified: bool = True
    company_size: Optional[str] = None
    job_title: str
    ai_score_threshold: int
    num_positions: int
    work_modes_list: List[str]
    visa_sponsorships_list: List[str]
    location_label: Optional[str] = None
    posted_ago: str
    new_applicants_count: int
    shortlisted_count: int
    deadline_label: Optional[str] = None
    status: bool
    status_label: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_range_label: Optional[str] = None
    is_valid: bool = False
    experience: Optional[str] = None
    employment_type: Optional[str] = None
    deadline: Optional[datetime] = None
    Deadline: Optional[str] = Field(default=None, alias="Deadline")
    Employment_Type: Optional[str] = Field(default=None, alias="Employment Type")
    pipeline_summary: PipelineStageSummary
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    company_details: EmployerCompanyDetails

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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
    is_viewed: bool = False

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
    is_viewed: bool = False

    model_config = ConfigDict(from_attributes=True)


class JobApplicationStatusUpdateRequest(BaseModel):
    status: str


class JobApplicationStatusUpdateResponse(BaseModel):
    application_id: UUID
    candidate_id: UUID
    job_id: UUID
    status: str
    status_label: str
    job_closed_automatically: bool = False


class JobPosterJobsStatsResponse(BaseModel):
    active: int
    closed: int
    draft: int
    expired: int

    model_config = ConfigDict(from_attributes=True)


class JobSaveDraft(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    employment_type_id: Optional[int] = None
    work_mode_id: Optional[int] = None
    city_id: Optional[int] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency_id: Optional[int] = None
    application_deadline: Optional[int] = None
    min_experience_years: Optional[int] = None
    max_experience_years: Optional[int] = None
    requires_visa_sponsorship: Optional[int] = None
    visa_sponsorship_ids: Optional[List[int]] = None
    num_positions: Optional[int] = None

    # Job flow fields
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None

    # Work authorization
    must_be_authorized_to_work: Optional[bool] = None
    us_citizen_or_pr_only: Optional[bool] = None
    security_clearance_required: Optional[bool] = None
    ai_score_threshold: Optional[int] = None

    # Cover letter
    include_cover_letter: Optional[bool] = None
    cover_letter_required: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class BulkStatusUpdateRequest(BaseModel):
    candidate_ids: List[UUID]
    status: str


class BulkStatusUpdateResponse(BaseModel):
    updated_count: int
    updated_applicants: List[JobApplicationStatusUpdateResponse]
