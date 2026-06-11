from datetime import datetime
from typing import List, Optional
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


class AdminCandidateDashboardResponse(BaseModel):
    title: str
    total_candidates: int
    active_ratio: float
    active_ratio_label: str
    active_candidates: int
    active_label: str
    suspended_candidates: int
    suspended_label: str

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


class AdminOrganizationBadge(BaseModel):
    label: str
    variant: str

    model_config = ConfigDict(from_attributes=True)


class AdminOrganizationHeader(BaseModel):
    id: UUID
    name: str
    initials: str
    logo_url: Optional[str] = None
    organization_type_id: Optional[int] = None
    organization_type_name: Optional[str] = None
    organization_type_label: str
    is_active: bool
    status_label: str
    status_badge: AdminOrganizationBadge
    onboarding_step: int
    onboarding_completed: bool
    onboarding_badge: AdminOrganizationBadge
    created_at: datetime
    created_label: str

    model_config = ConfigDict(from_attributes=True)


class AdminOrganizationCorporateDetail(BaseModel):
    key: str
    label: str
    value: Optional[str] = None
    value_label: str

    model_config = ConfigDict(from_attributes=True)


class AdminOrganizationAboutCompany(BaseModel):
    title: str
    description: Optional[str] = None
    description_label: str

    model_config = ConfigDict(from_attributes=True)


class AdminOrganizationJobOpeningsSummary(BaseModel):
    title: str
    count: int
    count_label: str
    description: str
    jobs_endpoint: str

    model_config = ConfigDict(from_attributes=True)


class AdminOrganizationDetailResponse(BaseModel):
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
    location_label: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    header: AdminOrganizationHeader
    corporate_details: List[AdminOrganizationCorporateDetail]
    about_company: AdminOrganizationAboutCompany
    job_openings_summary: AdminOrganizationJobOpeningsSummary

    model_config = ConfigDict(from_attributes=True)


class AdminOrganizationDashboardResponse(BaseModel):
    title: str
    total_organizations: int
    active_ratio: float
    active_ratio_label: str
    active_organizations: int
    active_label: str
    suspended_organizations: int
    suspended_label: str

    model_config = ConfigDict(from_attributes=True)


class AdminPlatformGrowthDataPoint(BaseModel):
    label: str
    bucket_start: datetime
    candidates: int
    employers: int

    model_config = ConfigDict(from_attributes=True)


class AdminPlatformGrowthAnalyticsResponse(BaseModel):
    title: str
    description: str
    period: str
    candidates_label: str
    employers_label: str
    data: List[AdminPlatformGrowthDataPoint]

    model_config = ConfigDict(from_attributes=True)


class AdminHiringFunnelDataPoint(BaseModel):
    title: str
    count: int
    count_label: str
    platform_count: int
    platform_count_label: str
    tooltip_title: str
    tooltip_platform_count_label: str

    model_config = ConfigDict(from_attributes=True)


class AdminHiringFunnelAnalyticsResponse(BaseModel):
    title: str
    description: str
    data: List[AdminHiringFunnelDataPoint]

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


class AdminCandidateResumeResponse(BaseModel):
    id: UUID
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    version_number: int
    is_primary: bool
    total_experience_years: int
    taxonomy_domain_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateApplicationResponse(BaseModel):
    id: UUID
    job_id: UUID
    job_title: str
    company_name: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateDetailResponse(BaseModel):
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
    visa_status_name: Optional[str] = None
    is_active: bool
    plan_tier: str
    daily_apply_credits_used: int
    monthly_ai_credits_used: int
    resume_optimizations_used_this_month: int
    cover_letters_generated_this_month: int
    last_credits_reset_at: datetime
    monthly_credits_reset_at: datetime
    created_at: datetime
    updated_at: datetime

    resumes: List[AdminCandidateResumeResponse] = []
    applications: List[AdminCandidateApplicationResponse] = []

    model_config = ConfigDict(from_attributes=True)


class AdminJobAnalyticsByDomainDataPoint(BaseModel):
    domain_name: str
    count: int

    model_config = ConfigDict(from_attributes=True)


class AdminJobAnalyticsByDomainResponse(BaseModel):
    title: str
    description: str
    data: List[AdminJobAnalyticsByDomainDataPoint]

    model_config = ConfigDict(from_attributes=True)


class AdminSkillCategoryDataPoint(BaseModel):
    title: str
    count: int
    count_label: str
    platform_count: int
    platform_count_label: str
    tooltip_title: str
    tooltip_platform_count_label: str

    model_config = ConfigDict(from_attributes=True)


class AdminSkillCategoriesResponse(BaseModel):
    title: str
    description: str
    data: List[AdminSkillCategoryDataPoint]

    model_config = ConfigDict(from_attributes=True)


class AdminGeographicAnalyticsDataPoint(BaseModel):
    location_name: str
    count: int
    count_label: str
    platform_count: int
    platform_count_label: str
    tooltip_title: str
    tooltip_platform_count_label: str

    model_config = ConfigDict(from_attributes=True)


class AdminGeographicAnalyticsResponse(BaseModel):
    title: str
    description: str
    data: List[AdminGeographicAnalyticsDataPoint]

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateAnalyticsByDomainDataPoint(BaseModel):
    domain_name: str
    count: int

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateAnalyticsByDomainResponse(BaseModel):
    title: str
    description: str
    data: List[AdminCandidateAnalyticsByDomainDataPoint]

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateExperienceLevelsDataPoint(BaseModel):
    experience_level: str
    count: int

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateExperienceLevelsResponse(BaseModel):
    title: str
    description: str
    data: List[AdminCandidateExperienceLevelsDataPoint]

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateSkillDensityDataPoint(BaseModel):
    skill_name: str
    count: int

    model_config = ConfigDict(from_attributes=True)


class AdminCandidateSkillDensityResponse(BaseModel):
    title: str
    description: str
    data: List[AdminCandidateSkillDensityDataPoint]

    model_config = ConfigDict(from_attributes=True)





