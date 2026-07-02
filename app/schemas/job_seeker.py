from datetime import datetime
from typing import List, Optional, Union, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.schemas.job import JobDashboardCardResponse

class CandidateCreditsResponse(BaseModel):
    plan_tier: str
    plan_name: str
    daily_apply_credits_limit: int
    daily_apply_credits_used: int
    daily_apply_credits_remaining: int
    monthly_ai_credits_limit: int
    monthly_ai_credits_used: int
    daily_credits_reset_in_seconds: int
    monthly_credits_reset_in_seconds: int
    resume_optimizations_used: int
    resume_optimizations_limit: Union[int, str]
    cover_letters_generated: int
    cover_letters_limit: Union[int, str]
    missing_skills_analysis_enabled: bool
    saved_resumes_limit: Union[int, str]
    monthly_reset_date: datetime

    model_config = ConfigDict(from_attributes=True)

class WeekdayStatus(BaseModel):
    day: str  # "MO", "TU", "WE", "TH", "FR", "SA", "SU"
    applied: bool

class CandidateCreditsScoreResponse(BaseModel):
    plan_tier: str
    plan_name: str
    current_streak: int
    running_week: List[WeekdayStatus]
    daily_apply_credits_limit: int
    daily_apply_credits_used: int
    daily_apply_credits_remaining: int
    monthly_ai_credits_limit: int
    monthly_ai_credits_used: int
    monthly_reset_date: datetime

    model_config = ConfigDict(from_attributes=True)

class JobSeekerFeedResponse(JobDashboardCardResponse):
    saved: bool = False
    applied: bool = False
    application_status: Optional[str] = None
    apply_mode: Optional[str] = None
    coverLetter: Optional[bool] = None

class AIMatchOverview(BaseModel):
    experience_match_percent: int
    skill_match_percent: int
    industry_fit_percent: int
    resume_alignment_percent: int
    matching_skills: List[str]
    resume_gaps: List[str]

class JobSeekerDetailResponse(BaseModel):
    id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    company_description: Optional[str] = None
    company_website: Optional[str] = None
    company_founded_year: Optional[int] = None
    company_location: Optional[str] = None
    company_size: Optional[str] = None
    company_rating: Optional[float] = None
    job_title: str
    job_overview: Optional[str] = None
    about_role: Optional[str] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    ai_score: Optional[int] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    location_label: Optional[str] = None
    work_mode: Optional[str] = None
    sponsorship_label: Optional[str] = None
    posted_ago: Optional[str] = None
    experience_label: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_range_label: Optional[str] = None
    employment_type: Optional[str] = None
    saved: bool = False
    applied: bool = False
    application_status: Optional[str] = None
    apply_mode: Optional[str] = None
    coverLetter: Optional[bool] = None
    ai_match_overview: Optional[AIMatchOverview] = None

    model_config = ConfigDict(from_attributes=True)

class SavedJobResponse(BaseModel):
    id: UUID
    job_id: UUID
    job_title: str
    company_name: Optional[str] = None
    saved_at: datetime

    model_config = ConfigDict(from_attributes=True)

class JobApplicationResponse(BaseModel):
    id: UUID
    job_id: UUID
    job_title: str
    company_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    status: str
    apply_mode: Optional[str] = None
    applied_at: datetime
    match_score: Optional[int] = None
    location_label: Optional[str] = None
    status_label: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobApplicationSubmitRequest(BaseModel):
    resume_url: str
    resume_name: str
    cover_letter_url: Optional[str] = None


class JobApplicationSubmitDetail(BaseModel):
    job_id: UUID
    applied_at: datetime
    resume_url: str
    cover_letter_url: Optional[str] = None


class JobApplicationSubmitResponse(BaseModel):
    status: str = "success"
    message: str = "Successfully applied to job!"
    application: JobApplicationSubmitDetail

class OptimizeSectionResult(BaseModel):
    section_type: str
    original_content: str
    optimized_content: str
    optimization_feedback: Optional[str] = None

class OptimizeResumeResponse(BaseModel):
    optimized_sections: List[OptimizeSectionResult]

class CoverLetterResponse(BaseModel):
    cover_letter: str

class FitAnalysisResponse(BaseModel):
    final_score: int
    experience_match_percent: int
    skill_match_percent: int
    industry_fit_percent: int
    resume_alignment_percent: int
    matching_skills: List[str]
    missing_keywords: List[str]


class ResumeVersionResponse(BaseModel):
    id: UUID
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    version_number: int
    is_primary: bool
    created_at: datetime
    job_id: Optional[UUID] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    ai_score: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ResumeUploadRequest(BaseModel):
    file_name: str
    file_url: str


class CoverLetterDetailResponse(BaseModel):
    id: UUID
    job_id: Optional[UUID] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    title: str
    content: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    ai_score: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CoverLetterCreateRequest(BaseModel):
    job_id: Optional[UUID] = None
    title: Optional[str] = None
    content: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None


class CoverLetterUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class SavedJobsStatusResponse(BaseModel):
    high_match_count: int
    visa_sponsored_count: int
    closing_soon_count: int
    needs_resume_update_count: int
    need_resume_upload_count: int
    status: Optional[str] = None
    count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SaveJobRequest(BaseModel):
    status: Optional[str] = None


class JobReportCreate(BaseModel):
    reason: Literal[
        "Fake or Misleading Job Post",
        "Spam or Promotional Content",
        "Suspicious Hiring Activity",
        "Discrimination or Harassment",
        "Inaccurate Company Info",
        "Duplicate Job Listings",
        "Scam or Fraud",
        "Other"
    ]
    description: Optional[str] = None


class JobReportResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    job_id: UUID
    reason: str
    description: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidatePreferencesRequest(BaseModel):
    role_type: Optional[str] = None
    preferred_location: Optional[str] = None
    min_salary: Optional[int] = None


class CandidatePreferencesResponse(BaseModel):
    role_type: Optional[str] = None
    preferred_location: Optional[str] = None
    min_salary: Optional[int] = None
    preferences_exist: bool

    model_config = ConfigDict(from_attributes=True)

class CandidateProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    phone: Optional[str] = None
    profile_picture: Optional[str] = None
    onboarding_step: int
    onboarding_completed: bool
    work_status_id: Optional[int] = None
    taxonomy_domain_id: Optional[int] = None
    visa_status_id: Optional[int] = None
    pref_role_type: Optional[str] = None
    pref_locations: Optional[str] = None
    pref_min_salary: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class CandidateProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    profile_picture: Optional[str] = None
    work_status_id: Optional[int] = None
    taxonomy_domain_id: Optional[int] = None
    visa_status_id: Optional[int] = None
    pref_role_type: Optional[str] = None
    pref_locations: Optional[str] = None
    pref_min_salary: Optional[int] = None



