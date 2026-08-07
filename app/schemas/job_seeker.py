from datetime import datetime
from typing import List, Optional, Union, Dict, Any, Literal
from uuid import UUID
import re
from pydantic import BaseModel, ConfigDict, field_validator, Field
from app.schemas.job import JobDashboardCardResponse, convert_text_to_bullets

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

class ScoredResumeResponse(BaseModel):
    resume_id: UUID
    resume_name: Optional[str] = None
    ats_score: int
    is_default: bool

    model_config = ConfigDict(from_attributes=True)


class JobSeekerFeedResponse(JobDashboardCardResponse):
    saved: bool = False
    applied: bool = False
    application_status: Optional[str] = None
    apply_mode: Optional[str] = None
    coverLetter: Optional[bool] = None
    resumes: List[ScoredResumeResponse] = []

class AIMatchOverview(BaseModel):
    experience_match_percent: int
    skill_match_percent: int
    industry_fit_percent: int
    resume_alignment_percent: int
    matching_skills: List[str]
    resume_gaps: List[str]
    resume_id: Optional[UUID] = None

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
    about_role: Optional[List[str]] = None
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

    @field_validator("about_role", mode="before")
    @classmethod
    def validate_about_role(cls, v):
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return convert_text_to_bullets(v)
        return v

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
    
    # Salary and Experience details
    experience_min_years: Optional[int] = None
    experience_max_years: Optional[int] = None
    experience_label: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency_code: Optional[str] = None
    salary_currency_symbol: Optional[str] = None
    salary_range_label: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobApplicationSubmitRequest(BaseModel):
    resume_url: str
    resume_name: str
    resume_id: Optional[UUID] = None
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

class SectionComparisonResult(BaseModel):
    section_type: str
    original_content: Optional[str] = None
    optimized_content: Optional[str] = None
    missing_keywords: List[str] = []
    optimization_feedback: Optional[str] = None

class OptimizeResumeResponse(BaseModel):
    optimized_sections: List[OptimizeSectionResult]

class CoverLetterResponse(BaseModel):
    cover_letter: str

class CoverLetterGenerateRequest(BaseModel):
    customization: Optional[str] = None

class FitAnalysisResponse(BaseModel):
    final_score: int
    experience_match_percent: int
    skill_match_percent: int
    industry_fit_percent: int
    resume_alignment_percent: int
    matching_skills: List[str]
    missing_keywords: List[str]
    resume_id: Optional[UUID] = None

class ResumeAnalyzeFitRequest(BaseModel):
    job_id: UUID = Field(..., alias="job_id")
    model_config = ConfigDict(populate_by_name=True)

class ResumeAnalyzeFitResponse(BaseModel):
    score: int
    match_status: str
    status_message: str
    gaps: List[str]
    strengths: List[str]

class AISuggestionItem(BaseModel):
    title: str
    description: str
    impact: Literal["high", "medium", "low"]

class ResumeSuggestionsResponse(BaseModel):
    missing_keywords: List[str]
    ai_suggestions: List[AISuggestionItem]


class ResumeVersionResponse(BaseModel):
    id: UUID
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    version_number: int
    is_primary: bool
    is_default: bool = False
    is_ai_optimized: bool = False
    created_at: datetime
    job_id: Optional[UUID] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    ai_score: Optional[int] = None
    strong_match: bool = False
    strong_match_roles: List[str] = []
    strong_match_role: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ResumeStructureResponse(BaseModel):
    id: UUID
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    original_file_url: Optional[str] = None
    version_number: int
    is_primary: bool
    is_ai_optimized: bool = False
    parent_resume_id: Optional[UUID] = None
    total_experience_years: int
    extracted_skills: List[str] = []
    taxonomy_domain_id: Optional[int] = None
    taxonomy_domain_name: Optional[str] = None
    sections: Dict[str, Optional[str]] = {}
    sections_comparison: List[SectionComparisonResult] = []
    original_structured_data: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OptimizeSectionRequest(BaseModel):
    job_id: Optional[UUID] = None


class ResumeUploadRequest(BaseModel):
    file_name: str
    file_url: str


class ResumeRenameRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255, description="The new filename for the resume")



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
    all_count: int
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
    current_address: Optional[str] = None
    experience_level: Optional[str] = None
    experience_years: Optional[int] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    about_summary: Optional[str] = None
    is_phone_verified: bool = False
    pref_role_type: Optional[str] = None
    pref_locations: Optional[str] = None
    pref_min_salary: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class CandidateProfileUpdate(BaseModel):
    full_name: str
    phone: str
    current_address: Optional[str] = None
    profile_picture: Optional[str] = None
    visa_status_id: Optional[int] = None
    work_status_id: Optional[int] = None
    taxonomy_domain_id: Optional[int] = None
    experience_level: Optional[Literal["0-1", "1-3", "3-5", "5-7", "7-10", "10+"]] = None
    experience_years: Optional[int] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    about_summary: Optional[str] = None
    pref_role_type: Optional[str] = None
    pref_locations: Optional[str] = None
    pref_min_salary: Optional[int] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("full_name is required and cannot be empty")
        return v.strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            raise ValueError("phone must be in a valid international format (e.g. +14155552671)")
        return v

    @field_validator("current_address")
    @classmethod
    def validate_current_address(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_stripped = v.strip()
        if v_stripped == "":
            return None
        return v_stripped

    @field_validator("experience_years")
    @classmethod
    def validate_experience_years(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 0 or v > 50):
            raise ValueError("experience_years must be between 0 and 50")
        return v

    @field_validator("linkedin_url", "portfolio_url")
    @classmethod
    def validate_https_url(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v_str = str(v).strip()
            if v_str == "":
                return None
            if not v_str.startswith("https://"):
                raise ValueError("URL must start with https://")
            return v_str
        return v

    @field_validator("about_summary")
    @classmethod
    def validate_about_summary(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 2600:
            raise ValueError("about_summary cannot exceed 2600 characters")
        return v


class SendOTPRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            raise ValueError("phone must be in a valid international format (e.g. +14155552671)")
        return v


class SendOTPResponse(BaseModel):
    message: str


class VerifyOTPRequest(BaseModel):
    phone: str
    otp_code: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^\+[1-9]\d{1,14}$", v):
            raise ValueError("phone must be in a valid international format (e.g. +14155552671)")
        return v

    @field_validator("otp_code")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("otp_code must be exactly 6 digits")
        return v


class VerifyOTPResponse(BaseModel):
    message: str
    is_phone_verified: bool


class JobApplicationStatsResponse(BaseModel):
    applied: int = 0
    under_review: int = 0
    shortlisted: int = 0
    interviewing: int = 0
    on_hold: int = 0
    offered: int = 0
    hired: int = 0
    rejected: int = 0
    total: int = 0


class ResumePDFRequest(BaseModel):
    resume_id: Optional[UUID] = None
    structured_data: Optional[Dict[str, Any]] = None
    resume_data: Optional[Dict[str, Any]] = None
    html_content: Optional[str] = None




class PaginatedResumeVersionResponse(BaseModel):
    resumes: List[ResumeVersionResponse]
    count: int


class AutoApplyStatusResponse(BaseModel):
    is_cancelled: bool
    daily_apply_credits_used: int
    daily_apply_limit: int
    remaining_daily_credits: int
    plan_tier: str

    model_config = ConfigDict(from_attributes=True)


class AutoApplyCancelResponse(BaseModel):
    message: str = "Auto-apply cancelled successfully."
    is_cancelled: bool = True


class PaginatedCoverLetterDetailResponse(BaseModel):
    cover_letters: List[CoverLetterDetailResponse]
    count: int


class JobResumeOptimizeSection(BaseModel):
    section_type: str
    keywords: List[str]


class JobResumeOptimizeRequest(BaseModel):
    keywords: Optional[List[str]] = None
    sections: Optional[List[JobResumeOptimizeSection]] = None


class OptimizeForJobRequest(BaseModel):
    job_id: UUID
    keywords: Optional[List[str]] = None
    sections: Optional[List[JobResumeOptimizeSection]] = None


class GeneralAnalysisRequest(BaseModel):
    target_role: Optional[str] = None


class GeneralAnalysisResponse(BaseModel):
    target_role: str
    gaps: List[str]
    strengths: List[str]
    suggested_keywords: List[str]


class GeneralOptimizeRequest(BaseModel):
    target_role: Optional[str] = None
    keywords: List[str]
    sections: Optional[List[str]] = None








