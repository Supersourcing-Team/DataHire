from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, select, func, case

from app.db.session import get_db
from app.core.dependencies import require_candidate, get_current_active_user
from app.models.user import User, UserRole
from app.models.candidate import Candidate, CandidateSkippedJob
from app.models.job import JobPosting, JobStatus
from app.models.company import Company
from app.models.application import JobApplication
from app.models.saved_job import SavedJob
from app.models.resume import Resume, ResumeSection, SectionType
from app.models.cover_letter import CoverLetter
from app.models.job_report import JobReport
from app.services.matching_engine import MatchingEngine
from app.services.optimization_engine import optimization_engine
from app.services.credit_manager import CreditManager, credit_manager
from app.services.pdf_service import pdf_service
from app.services.embedding_service import embedding_service
from app.schemas.job_seeker import (
    ResumePDFRequest,
    ResumeAnalyzeFitRequest,
    ResumeAnalyzeFitResponse,
    AISuggestionItem,
    ResumeSuggestionsResponse,
    CandidateCreditsResponse,
    CandidateCreditsScoreResponse,
    WeekdayStatus,
    CandidateProfileResponse,
    CandidateProfileUpdate,
    JobSeekerFeedResponse,
    JobSeekerDetailResponse,
    AIMatchOverview,
    SavedJobResponse,
    SavedJobsStatusResponse,
    JobApplicationResponse,
    JobApplicationStatsResponse,
    OptimizeResumeResponse,
    OptimizeSectionResult,
    OptimizeSectionRequest,
    CoverLetterResponse,
    CoverLetterGenerateRequest,
    FitAnalysisResponse,
    ResumeVersionResponse,
    PaginatedResumeVersionResponse,
    ResumeStructureResponse,
    ResumeUploadRequest,
    CoverLetterDetailResponse,
    PaginatedCoverLetterDetailResponse,
    CoverLetterCreateRequest,
    CoverLetterUpdateRequest,
    SaveJobRequest,
    JobReportCreate,
    JobReportResponse,
    CandidatePreferencesRequest,
    CandidatePreferencesResponse,
    JobApplicationSubmitRequest,
    JobApplicationSubmitDetail,
    JobApplicationSubmitResponse,
    SendOTPRequest,
    SendOTPResponse,
    VerifyOTPRequest,
    VerifyOTPResponse
)
from app.models.meta import MetaWorkStatus, MetaVisaStatus
from app.models.taxonomy import TaxonomyDomain
from app.services.otp_service import OTPService
from app.services.s3_service import S3Service
from app.schemas.job import JobPosterApplicantProfileResponse, TimelineEvent
from app.api.v1.jobs import (
    _build_location_label,
    _format_experience_label,
    _format_posted_ago,
    _format_salary_range,
    _build_sponsorship_label
)


router = APIRouter(prefix="/job-seeker", tags=["job-seeker"])
s3_service = S3Service()

# Plan Limits configuration
PLAN_LIMITS = {
    "free": {
        "name": "Free",
        "daily_apply_limit": 0,
        "monthly_ai_credits": 150,
        "monthly_resume_optimization_limit": 4,
        "monthly_cover_letter_limit": 0, # Manual upload only
        "missing_skills_analysis_enabled": False,
        "saved_resumes_limit": 7,
    },
    "silver": {
        "name": "Silver",
        "daily_apply_limit": 3,
        "monthly_ai_credits": 800,
        "monthly_resume_optimization_limit": 15,
        "monthly_cover_letter_limit": 100,
        "missing_skills_analysis_enabled": True,
        "saved_resumes_limit": 30,
    },
    "gold": {
        "name": "Gold",
        "daily_apply_limit": 5,
        "monthly_ai_credits": 1200,
        "monthly_resume_optimization_limit": 22,
        "monthly_cover_letter_limit": 500,
        "missing_skills_analysis_enabled": True,
        "saved_resumes_limit": 50,
    },
    "platinum": {
        "name": "Platinum",
        "daily_apply_limit": 9999,
        "monthly_ai_credits": 99999,
        "monthly_resume_optimization_limit": 50,
        "monthly_cover_letter_limit": 1000,
        "missing_skills_analysis_enabled": True,
        "saved_resumes_limit": 100,
    }
}

def get_candidate(current_user: User, db: Session) -> Candidate:
    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate profile not found."
        )
    return candidate

def check_and_reset_candidate_credits(candidate: Candidate, db: Session) -> Candidate:
    now = datetime.now(timezone.utc)
    
    # Check daily reset (UTC day boundary)
    last_reset_utc = candidate.last_credits_reset_at.astimezone(timezone.utc) if candidate.last_credits_reset_at.tzinfo else candidate.last_credits_reset_at.replace(tzinfo=timezone.utc)
    if last_reset_utc.date() < now.date():
        candidate.daily_apply_credits_used = 0
        candidate.last_credits_reset_at = now
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        
    # Check monthly reset (UTC month boundary)
    last_monthly_reset_utc = candidate.monthly_credits_reset_at.astimezone(timezone.utc) if candidate.monthly_credits_reset_at.tzinfo else candidate.monthly_credits_reset_at.replace(tzinfo=timezone.utc)
    if last_monthly_reset_utc.year < now.year or last_monthly_reset_utc.month < now.month:
        candidate.monthly_ai_credits_used = 0
        candidate.resume_optimizations_used_this_month = 0
        candidate.cover_letters_generated_this_month = 0
        candidate.monthly_credits_reset_at = now
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        
    return candidate

@router.get("/dashboard/credits", response_model=CandidateCreditsResponse)
def get_dashboard_credits(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    now = datetime.now(timezone.utc)
    next_day = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    daily_reset_sec = int((next_day - now).total_seconds())
    
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    monthly_reset_sec = int((next_month - now).total_seconds())
    
    return CandidateCreditsResponse(
        plan_tier=tier,
        plan_name=limits["name"],
        daily_apply_credits_limit=limits["daily_apply_limit"],
        daily_apply_credits_used=candidate.daily_apply_credits_used,
        daily_apply_credits_remaining=max(0, limits["daily_apply_limit"] - candidate.daily_apply_credits_used),
        monthly_ai_credits_limit=limits["monthly_ai_credits"],
        monthly_ai_credits_used=candidate.monthly_ai_credits_used,
        daily_credits_reset_in_seconds=daily_reset_sec,
        monthly_credits_reset_in_seconds=monthly_reset_sec,
        resume_optimizations_used=candidate.resume_optimizations_used_this_month,
        resume_optimizations_limit=limits["monthly_resume_optimization_limit"] if limits["monthly_resume_optimization_limit"] < 9999 else "Unlimited",
        cover_letters_generated=candidate.cover_letters_generated_this_month,
        cover_letters_limit=limits["monthly_cover_letter_limit"] if limits["monthly_cover_letter_limit"] < 9999 else "Unlimited",
        missing_skills_analysis_enabled=limits["missing_skills_analysis_enabled"],
        saved_resumes_limit=limits["saved_resumes_limit"] if limits["saved_resumes_limit"] < 9999 else "Unlimited",
        monthly_reset_date=next_month
    )

@router.get("/dashboard/credits-score", response_model=CandidateCreditsScoreResponse)
def get_dashboard_credits_score(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    # Calculate next monthly reset date
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        
    # --- Streak Calculation ---
    # Fetch distinct dates of auto-applies for this candidate in UTC
    app_dates = (
        db.query(func.date(JobApplication.created_at))
        .filter(
            JobApplication.candidate_id == candidate.id,
            JobApplication.apply_mode == "auto-apply"
        )
        .distinct()
        .order_by(func.date(JobApplication.created_at).desc())
        .all()
    )
    
    dates_set = {r[0] for r in app_dates if r[0] is not None}
    today = now.date()
    
    current_streak = 0
    check_date = today
    
    # Keep streak active if they applied yesterday but haven't applied today yet
    if check_date not in dates_set:
        check_date = today - timedelta(days=1)
        
    while check_date in dates_set:
        current_streak += 1
        check_date -= timedelta(days=1)
        
    # --- Running Week (Monday to Sunday) Auto-Apply Map ---
    # Find Monday of the current running week
    # weekday() returns 0 for Monday, 6 for Sunday
    start_of_week = today - timedelta(days=today.weekday())
    
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    running_week = []
    
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        has_applied = day_date in dates_set
        running_week.append(
            WeekdayStatus(
                day=weekday_labels[i],
                applied=has_applied
            )
        )
        
    return CandidateCreditsScoreResponse(
        plan_tier=tier,
        plan_name=f"{limits['name']} Plan",
        current_streak=current_streak,
        running_week=running_week,
        daily_apply_credits_limit=limits["daily_apply_limit"],
        daily_apply_credits_used=candidate.daily_apply_credits_used,
        daily_apply_credits_remaining=max(0, limits["daily_apply_limit"] - candidate.daily_apply_credits_used),
        monthly_ai_credits_limit=limits["monthly_ai_credits"],
        monthly_ai_credits_used=candidate.monthly_ai_credits_used,
        monthly_reset_date=next_month
    )

@router.get("/dashboard/feed", response_model=List[JobSeekerFeedResponse])
def get_job_seeker_feed(
    search: Optional[str] = None,
    work_type: Optional[str] = None,
    job_type: Optional[str] = None,
    location: Optional[str] = None,
    match_score: Optional[str] = None,
    job_post_date: Optional[str] = None,
    visa_sponsorship: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    
    # 1. Start base query
    query = db.query(JobPosting).filter(JobPosting.is_active == True, JobPosting.status == JobStatus.PUBLISHED)
    
    # Apply search filter
    if search:
        query = query.join(Company).filter(
            or_(
                JobPosting.title.ilike(f"%{search}%"),
                Company.name.ilike(f"%{search}%")
            )
        )

    # Apply work type filter
    if work_type and work_type.lower() != "all":
        query = query.filter(JobPosting.work_mode.has(name=work_type.upper()))
        
    # Apply job type filter
    if job_type and job_type.lower() != "all":
        norm_jt = job_type.replace("-", "_").upper()

        query = query.filter(JobPosting.employment_type.has(name=norm_jt))
    # Apply location country filter
    if location and location.lower() != "all":
        if location.lower() in ("u.s.", "us", "united states"):
            query = query.join(JobPosting.country).filter(JobPosting.country.has(iso_code="US"))
        elif location.lower() in ("india", "in"):
            query = query.join(JobPosting.country).filter(JobPosting.country.has(iso_code="IN"))
            
    # Apply visa sponsorship filter
    if visa_sponsorship and visa_sponsorship.lower() != "all":
        if visa_sponsorship.lower() == "h1b sponsorship":
            query = query.filter(JobPosting.visa_status.has(name="H-1B Visa"))
        elif visa_sponsorship.lower() == "sponsorship available":
            query = query.filter(or_(JobPosting.requires_visa_sponsorship.isnot(None), JobPosting.must_be_authorized_to_work == False))
        elif visa_sponsorship.lower() == "no sponsorship":
            query = query.filter(JobPosting.requires_visa_sponsorship.is_(None))
            
    # Apply salary filters
    if salary_min is not None:
        query = query.filter(JobPosting.salary_min >= salary_min)
    if salary_max is not None:
        query = query.filter(JobPosting.salary_max <= salary_max)
        
    # Apply job post date filter
    if job_post_date:
        now = datetime.now(timezone.utc)
        if job_post_date.lower() == "today" or job_post_date.lower() == "within 24 hour":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=1))
        elif job_post_date.lower() == "last 7 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=7))
        elif job_post_date.lower() == "last 30 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=30))
            
    jobs = query.order_by(JobPosting.created_at.desc()).all()
    
    # 2. Get candidate primary resume for score calculations
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    
    matching_service = MatchingEngine(db)
    
    # 3. Process each job to add state & score
    feed_items = []
    for job in jobs:
        # Check if saved or applied
        is_saved = db.query(SavedJob).filter(SavedJob.candidate_id == candidate.id, SavedJob.job_id == job.id).first() is not None
        app_record = db.query(JobApplication).filter(JobApplication.candidate_id == candidate.id, JobApplication.job_id == job.id).first()
        is_applied = app_record is not None
        app_status = app_record.status if app_record else None
        
        # Calculate AI match score
        ai_score = 0
        if primary_resume and primary_resume.overall_embedding is not None:
            try:
                score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
                
        # Filter by Match Score in Python if specified
        if match_score and match_score.lower() != "all":
            if match_score == "90%+" and ai_score < 90:
                continue
            elif match_score == "80 – 89%" and not (80 <= ai_score <= 89):
                continue
            elif match_score == "70 – 79%" and not (70 <= ai_score <= 79):
                continue
            elif match_score == "Below 70%" and ai_score >= 70:
                continue
                
        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None
        
        feed_items.append(
            JobSeekerFeedResponse(
                id=job.id,
                company_id=job.company_id,
                company_name=job.company.name if job.company else None,
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
                company_verified=True,
                job_title=job.title,
                ai_score=ai_score,
                city=city_name,
                state=state_name,
                country=country_name,
                location_label=_build_location_label(city_name, state_name, country_name),
                work_mode=job.work_mode.name if job.work_mode else None,
                sponsorship_label=_build_sponsorship_label(job),
                posted_at=job.created_at,
                posted_ago=_format_posted_ago(job.created_at),
                experience_min_years=job.min_experience_years,
                experience_max_years=job.max_experience_years,
                experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
                salary_min=job.salary_min if job.salary_min is not None else None,
                salary_max=job.salary_max if job.salary_max is not None else None,
                salary_currency_code=currency_code,
                salary_currency_symbol=currency_symbol,
                salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code),
                employment_type=job.employment_type.name if job.employment_type else None,
                save_action="unsave" if is_saved else "save",
                apply_action="applied" if is_applied else "apply",
                saved=is_saved,
                applied=is_applied,
                application_status=app_status,
                apply_mode=app_record.apply_mode if app_record else None,
                coverLetter=job.cover_letter_required
            )
        )
        
    # Python-level pagination
    return feed_items[skip : skip + limit]

@router.get("/jobs/{job_id}", response_model=JobSeekerDetailResponse)
def get_job_seeker_job_details(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
        
    # Check save and application status
    is_saved = db.query(SavedJob).filter(SavedJob.candidate_id == candidate.id, SavedJob.job_id == job.id).first() is not None
    app_record = db.query(JobApplication).filter(JobApplication.candidate_id == candidate.id, JobApplication.job_id == job.id).first()
    is_applied = app_record is not None
    app_status = app_record.status if app_record else None
    
    # Get primary resume and match overview
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    
    ai_score = 0
    match_overview = None
    
    if primary_resume:
        matching_service = MatchingEngine(db)
        try:
            score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
            ai_score = int(score_details["final_score"])
            
            # Map breakdown percentages
            breakdown = score_details["breakdown"]
            insights = score_details["insights"]
            
            # Sub-percentages
            exp_pct = int(breakdown.get("experience", 0))
            skills_pct = int(breakdown.get("skills", 0))
            sem_pct = int(breakdown.get("semantic", 0))
            log_pct = int(breakdown.get("logistics", 0))
            
            # Dynamic missing skills check based on plan permissions
            plan_tier = candidate.plan_tier or "free"
            limits = PLAN_LIMITS.get(plan_tier, PLAN_LIMITS["free"])
            
            missing_skills = []
            if limits["missing_skills_analysis_enabled"]:
                missing_skills = insights.get("missing_skills", [])
                
            match_overview = AIMatchOverview(
                experience_match_percent=exp_pct,
                skill_match_percent=skills_pct,
                industry_fit_percent=log_pct,
                resume_alignment_percent=sem_pct,
                matching_skills=insights.get("matched_skills", []),
                resume_gaps=missing_skills
            )
        except Exception:
            pass
            
    city_name = job.city.name if job.city else None
    state_name = job.state.name if job.state else None
    country_name = job.country.name if job.country else None
    currency_code = job.currency.code if job.currency else None
    currency_symbol = job.currency.symbol if job.currency else None
    
    return JobSeekerDetailResponse(
        id=job.id,
        company_id=job.company_id,
        company_name=job.company.name if job.company else None,
        company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
        company_description=job.company.description if job.company else None,
        company_website=job.company.website if job.company else None,
        company_founded_year=job.company.founded_year if job.company else None,
        company_location=_build_location_label(
            job.company.city.name if job.company and job.company.city else None,
            job.company.state.name if job.company and job.company.state else None,
            job.company.country.name if job.company and job.company.country else None
        ),
        company_size=job.company.size.label if job.company and job.company.size else None,
        company_rating=4.2,  # Seed/Mocked
        job_title=job.title,
        job_overview=job.job_overview or job.description,
        about_role=job.about_role,
        requirements=job.requirements or [],
        responsibilities=job.responsibilities or [],
        benefits=job.benefits or [],
        ai_score=ai_score,
        city=city_name,
        state=state_name,
        country=country_name,
        location_label=_build_location_label(city_name, state_name, country_name),
        work_mode=job.work_mode.name if job.work_mode else None,
        sponsorship_label=_build_sponsorship_label(job),
        posted_ago=_format_posted_ago(job.created_at),
        experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
        salary_min=job.salary_min * 12 if job.salary_min is not None else None,
        salary_max=job.salary_max * 12 if job.salary_max is not None else None,
        salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code),
        employment_type=job.employment_type.name if job.employment_type else None,
        saved=is_saved,
        applied=is_applied,
        application_status=app_status,
        apply_mode=app_record.apply_mode if app_record else None,
        coverLetter=job.cover_letter_required,
        ai_match_overview=match_overview
    )

@router.post("/jobs/{job_id}/apply", response_model=JobApplicationSubmitResponse)
def apply_to_job(
    job_id: UUID,
    payload: JobApplicationSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    # Check if already applied
    existing_app = db.query(JobApplication).filter(JobApplication.candidate_id == candidate.id, JobApplication.job_id == job.id).first()
    if existing_app:
        raise HTTPException(status_code=400, detail="You have already applied to this job.")
        
    # Resolve the resume passed in payload
    # 1. Prioritize a resume matching the URL that is already linked to this job (e.g. optimized)
    resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.file_url == payload.resume_url,
        Resume.job_id == job.id
    ).first()
    
    # 2. Fall back to any resume matching the URL if no job-linked version exists
    if not resume:
        resume = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.file_url == payload.resume_url
        ).first()
    if not resume:
        # Check saved resumes limit
        tier = candidate.plan_tier or "free"
        limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
        existing_resumes_count = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.is_deleted == False
        ).count()
        if existing_resumes_count >= limits["saved_resumes_limit"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You have reached your limit of {limits['saved_resumes_limit']} saved resumes. Please delete an existing resume to apply with a new one."
            )
            
        # Create a new resume record copying metadata from primary resume
        primary_res = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.is_primary == True
        ).first()
        
        resume = Resume(
            candidate_id=candidate.id,
            file_url=payload.resume_url,
            file_name=payload.resume_name,
            job_id=job.id,
            parent_resume_id=primary_res.id if primary_res else None,
            version_number=existing_resumes_count + 1,
            is_primary=False,
            is_ai_optimized=False,
            total_experience_years=0
        )
        if primary_res:
            resume.total_experience_years = primary_res.total_experience_years
            resume.taxonomy_domain_id = primary_res.taxonomy_domain_id
            resume.overall_embedding = primary_res.overall_embedding
            resume.extracted_skills = primary_res.extracted_skills
            resume.structured_data = primary_res.structured_data
            
        db.add(resume)
        db.flush()
        
        if primary_res:
            from app.models.resume import ResumeSection
            for section in primary_res.sections:
                new_section = ResumeSection(
                    resume_id=resume.id,
                    section_type=section.section_type,
                    original_content=section.original_content,
                    optimized_content=section.optimized_content,
                    optimization_metadata=section.optimization_metadata,
                    structured_content=section.structured_content,
                    optimized_structured_content=section.optimized_structured_content
                )
                db.add(new_section)
            db.flush()
    else:
        # If it was soft-deleted, check limit and restore
        if resume.is_deleted:
            tier = candidate.plan_tier or "free"
            limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
            existing_resumes_count = db.query(Resume).filter(
                Resume.candidate_id == candidate.id,
                Resume.is_deleted == False
            ).count()
            if existing_resumes_count >= limits["saved_resumes_limit"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"You have reached your limit of {limits['saved_resumes_limit']} saved resumes. Please delete an existing resume to reuse this one."
                )
            resume.is_deleted = False
            
        # Link existing resume to this job if not already
        if resume.job_id != job.id:
            resume.job_id = job.id
            if not resume.parent_resume_id:
                primary_res = db.query(Resume).filter(
                    Resume.candidate_id == candidate.id,
                    Resume.is_primary == True
                ).first()
                if primary_res and resume.id != primary_res.id:
                    resume.parent_resume_id = primary_res.id
            db.flush()

    # Calculate AI score for this application using the selected resume
    ai_score = 0
    if resume and resume.overall_embedding is not None:
        try:
            matching_service = MatchingEngine(db)
            score_details = matching_service.score_resume_for_job(resume.id, job.id)
            ai_score = int(score_details["final_score"])
        except Exception:
            ai_score = 0

    # Determine status: "shortlisted" if ai_score matches or exceeds job's threshold (or default 70)
    threshold = job.ai_score_threshold if (job.ai_score_threshold and job.ai_score_threshold > 0) else 70
    app_status = "shortlisted" if ai_score >= threshold else "applied"

    # Create application record
    new_app = JobApplication(
        candidate_id=candidate.id,
        job_id=job.id,
        status=app_status,
        apply_mode="apply",
        cover_letter=payload.cover_letter_url
    )
    
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    
    return JobApplicationSubmitResponse(
        status="success",
        message="Successfully applied to job!",
        application=JobApplicationSubmitDetail(
            job_id=new_app.job_id,
            applied_at=new_app.created_at,
            resume_url=payload.resume_url,
            cover_letter_url=payload.cover_letter_url
        )
    )


@router.post("/jobs/{job_id}/save-unsave")
def save_or_unsave_job(
    job_id: UUID,
    payload: Optional[SaveJobRequest] = None,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    existing_save = db.query(SavedJob).filter(SavedJob.candidate_id == candidate.id, SavedJob.job_id == job.id).first()
    
    # Resolve status from query parameters or request body payload
    requested_status = status or (payload.status if payload else None)
        
    if requested_status is not None:
        normalized_status = requested_status.lower().strip()
        if normalized_status == "save":
            if not existing_save:
                new_save = SavedJob(candidate_id=candidate.id, job_id=job.id)
                db.add(new_save)
                db.commit()
            return {"saved": True, "message": "Job saved successfully."}
        elif normalized_status == "unsave":
            if existing_save:
                db.delete(existing_save)
                db.commit()
            return {"saved": False, "message": "Job unsaved successfully."}
        else:
            raise HTTPException(status_code=400, detail="Invalid status. Supported statuses are 'save' and 'unsave'.")
            
    # Default to toggle behavior if no explicit status is requested
    if existing_save:
        # Unsave job
        db.delete(existing_save)
        db.commit()
        return {"saved": False, "message": "Job unsaved successfully."}
    else:
        # Save job
        new_save = SavedJob(candidate_id=candidate.id, job_id=job.id)
        db.add(new_save)
        db.commit()
        return {"saved": True, "message": "Job saved successfully."}


@router.post("/jobs/{job_id}/report", response_model=JobReportResponse, status_code=status.HTTP_201_CREATED)
def report_job(
    job_id: UUID,
    payload: JobReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
        
    existing_report = db.query(JobReport).filter(
        JobReport.candidate_id == candidate.id,
        JobReport.job_id == job_id
    ).first()
    
    if existing_report:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reported this job posting."
        )
        
    new_report = JobReport(
        candidate_id=candidate.id,
        job_id=job_id,
        reason=payload.reason,
        description=payload.description
    )
    
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    
    return new_report


@router.get("/saved-jobs", response_model=List[SavedJobResponse])
def get_saved_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    saved_records = db.query(SavedJob).filter(SavedJob.candidate_id == candidate.id).order_by(SavedJob.created_at.desc()).all()
    
    response = []
    for record in saved_records:
        response.append(
            SavedJobResponse(
                id=record.id,
                job_id=record.job_id,
                job_title=record.job.title if record.job else "Unknown Position",
                company_name=record.job.company.name if record.job and record.job.company else None,
                saved_at=record.created_at
            )
        )
    return response


@router.get("/dashboard/saved-jobs/pipeline-status", response_model=SavedJobsStatusResponse)
def get_saved_jobs_status(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    
    # 1. Fetch all saved records for candidate with eager loading of relations to prevent duplicate hits in the loop
    saved_records = (
        db.query(SavedJob)
        .filter(SavedJob.candidate_id == candidate.id)
        .options(
            joinedload(SavedJob.job).joinedload(JobPosting.company),
            joinedload(SavedJob.job).joinedload(JobPosting.city),
            joinedload(SavedJob.job).joinedload(JobPosting.state),
            joinedload(SavedJob.job).joinedload(JobPosting.country),
            joinedload(SavedJob.job).joinedload(JobPosting.currency),
            joinedload(SavedJob.job).joinedload(JobPosting.work_mode),
            joinedload(SavedJob.job).joinedload(JobPosting.employment_type),
        )
        .order_by(SavedJob.created_at.desc())
        .all()
    )
    
    # 2. Get candidate primary resume for score calculations
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    
    matching_service = MatchingEngine(db)
    
    high_match_count = 0
    visa_sponsored_count = 0
    closing_soon_count = 0
    needs_resume_update_count = 0
    
    now = datetime.now(timezone.utc)
    
    for record in saved_records:
        job = record.job
        if not job or not job.is_active:
            continue
            
        # Calculate AI match score using the central MatchingEngine with pre-loaded objects
        ai_score = 0
        if primary_resume and primary_resume.overall_embedding is not None:
            try:
                score_details = matching_service.score_resume_object_for_job_object(primary_resume, job)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
                
        # Determine status flags
        is_high_match = ai_score >= 80
        is_visa_sponsored = job.requires_visa_sponsorship is not None
        
        is_closing_soon = False
        if job.application_deadline:
            deadline_utc = job.application_deadline.astimezone(timezone.utc) if job.application_deadline.tzinfo else job.application_deadline.replace(tzinfo=timezone.utc)
            is_closing_soon = now <= deadline_utc <= now + timedelta(days=7)
            
        is_needs_resume_update = (primary_resume is None) or (ai_score < 80)
        
        # Increment counts
        if is_high_match:
            high_match_count += 1
        if is_visa_sponsored:
            visa_sponsored_count += 1
        if is_closing_soon:
            closing_soon_count += 1
        if is_needs_resume_update:
            needs_resume_update_count += 1
            
    # Calculate response count for the requested query parameter
    resp_status = None
    resp_count = None
    
    if status is not None:
        normalized_status = status.lower().replace("_", " ").strip()
        if normalized_status in ("highmatch", "high match", "high_match"):
            resp_status = status
            resp_count = high_match_count
        elif normalized_status in ("visa sponsored", "visa_sponsored"):
            resp_status = status
            resp_count = visa_sponsored_count
        elif normalized_status in ("closing soon", "closing_soon"):
            resp_status = status
            resp_count = closing_soon_count
        elif normalized_status in ("need resume upload", "needs resume update", "need_resume_upload", "needs_resume_update"):
            resp_status = status
            resp_count = needs_resume_update_count
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid status '{status}'. Supported statuses are: "
                    "'high_match', 'visa_sponsored', 'closing_soon', 'needs_resume_update'."
                )
            )

    return SavedJobsStatusResponse(
        high_match_count=high_match_count,
        visa_sponsored_count=visa_sponsored_count,
        closing_soon_count=closing_soon_count,
        needs_resume_update_count=needs_resume_update_count,
        need_resume_upload_count=needs_resume_update_count,
        status=resp_status,
        count=resp_count
    )


@router.get("/dashboard/saved-jobs/pipeline", response_model=List[JobSeekerFeedResponse])
def get_saved_jobs_pipeline(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    
    # 1. Fetch all saved records for candidate with eager loading of relations to prevent duplicate hits in the loop
    saved_records = (
        db.query(SavedJob)
        .filter(SavedJob.candidate_id == candidate.id)
        .options(
            joinedload(SavedJob.job).joinedload(JobPosting.company),
            joinedload(SavedJob.job).joinedload(JobPosting.city),
            joinedload(SavedJob.job).joinedload(JobPosting.state),
            joinedload(SavedJob.job).joinedload(JobPosting.country),
            joinedload(SavedJob.job).joinedload(JobPosting.currency),
            joinedload(SavedJob.job).joinedload(JobPosting.work_mode),
            joinedload(SavedJob.job).joinedload(JobPosting.employment_type),
        )
        .order_by(SavedJob.created_at.desc())
        .all()
    )
    
    # 2. Get candidate primary resume for score calculations
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    
    # 3. Batch query job applications for the candidate to avoid hitting database in the loop
    applications = db.query(JobApplication).filter(JobApplication.candidate_id == candidate.id).all()
    applications_map = {app.job_id: app for app in applications}
    
    matching_service = MatchingEngine(db)
    
    all_jobs_data = []
    
    now = datetime.now(timezone.utc)
    
    # Check if a query param status is requested and normalize it
    filter_high_match = False
    filter_visa_sponsored = False
    filter_closing_soon = False
    filter_need_resume_upload = False
    has_active_filter = False
    
    if status is not None:
        normalized_status = status.lower().replace("_", " ").strip()
        if normalized_status in ("highmatch", "high match", "high_match"):
            filter_high_match = True
            has_active_filter = True
        elif normalized_status in ("visa sponsored", "visa_sponsored"):
            filter_visa_sponsored = True
            has_active_filter = True
        elif normalized_status in ("closing soon", "closing_soon"):
            filter_closing_soon = True
            has_active_filter = True
        elif normalized_status in ("need resume upload", "needs resume update", "need_resume_upload", "needs_resume_update"):
            filter_need_resume_upload = True
            has_active_filter = True
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid status '{status}'. Supported statuses are: "
                    "'high_match', 'visa_sponsored', 'closing_soon', 'needs_resume_update'."
                )
            )

    for record in saved_records:
        job = record.job
        if not job or not job.is_active:
            continue
            
        # Get application status from batch-loaded dictionary (no duplicate query)
        app_record = applications_map.get(job.id)
        is_applied = app_record is not None
        app_status = app_record.status if app_record else None
        
        # Calculate AI match score using the central MatchingEngine with pre-loaded objects
        ai_score = 0
        if primary_resume and primary_resume.overall_embedding is not None:
            try:
                score_details = matching_service.score_resume_object_for_job_object(primary_resume, job)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
                
        # Determine status flags
        is_high_match = ai_score >= 80
        is_visa_sponsored = job.requires_visa_sponsorship is not None
        
        is_closing_soon = False
        if job.application_deadline:
            deadline_utc = job.application_deadline.astimezone(timezone.utc) if job.application_deadline.tzinfo else job.application_deadline.replace(tzinfo=timezone.utc)
            is_closing_soon = now <= deadline_utc <= now + timedelta(days=7)
            
        is_needs_resume_update = (primary_resume is None) or (ai_score < 80)
        
        # Apply filtering
        if has_active_filter:
            if filter_high_match and not is_high_match:
                continue
            if filter_visa_sponsored and not is_visa_sponsored:
                continue
            if filter_closing_soon and not is_closing_soon:
                continue
            if filter_need_resume_upload and not is_needs_resume_update:
                continue
            
        # Format the job attributes using existing helper methods
        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None
        
        feed_item = JobSeekerFeedResponse(
            id=job.id,
            company_id=job.company_id,
            company_name=job.company.name if job.company else None,
            company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
            company_verified=True,
            job_title=job.title,
            ai_score=ai_score,
            city=city_name,
            state=state_name,
            country=country_name,
            location_label=_build_location_label(city_name, state_name, country_name),
            work_mode=job.work_mode.name if job.work_mode else None,
            sponsorship_label=_build_sponsorship_label(job),
            posted_at=job.created_at,
            posted_ago=_format_posted_ago(job.created_at),
            experience_min_years=job.min_experience_years,
            experience_max_years=job.max_experience_years,
            experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
            salary_min=job.salary_min * 12 if job.salary_min is not None else None,
            salary_max=job.salary_max * 12 if job.salary_max is not None else None,
            salary_currency_code=currency_code,
            salary_currency_symbol=currency_symbol,
            salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code),
            employment_type=job.employment_type.name if job.employment_type else None,
            save_action="unsave",
            apply_action="applied" if is_applied else "apply",
            saved=True,
            applied=is_applied,
            application_status=app_status,
            coverLetter=job.cover_letter_required
        )
        
        all_jobs_data.append(feed_item)
        
    return all_jobs_data


@router.get("/applications", response_model=List[JobApplicationResponse])
def get_submitted_applications(
    status: Optional[str] = None,
    apply_mode: Optional[str] = None,
    search: Optional[str] = None,
    work_type: Optional[str] = None,
    job_type: Optional[str] = None,
    location: Optional[str] = None,
    match_score: Optional[str] = None,
    job_post_date: Optional[str] = None,
    visa_sponsorship: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    # Get primary resume for match score fallback
    primary_resume = db.query(Resume).filter(Resume.candidate_id == candidate.id, Resume.is_primary == True).first()
    
    # Base query for JobApplication, joining JobPosting
    query = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .options(
            joinedload(JobApplication.job).joinedload(JobPosting.company),
            joinedload(JobApplication.job).joinedload(JobPosting.city),
            joinedload(JobApplication.job).joinedload(JobPosting.state),
            joinedload(JobApplication.job).joinedload(JobPosting.work_mode),
            joinedload(JobApplication.job).joinedload(JobPosting.currency)
        )
        .filter(JobApplication.candidate_id == candidate.id)
    )

    # Filter by application status
    if status:
        status_lower = status.lower()
        if status_lower in ("interviewing", "interviewed", "interview"):
            query = query.filter(func.lower(JobApplication.status).in_(["interviewing", "interviewed", "interview"]))
        elif status_lower in ("onhold", "on_hold", "on hold"):
            query = query.filter(func.lower(JobApplication.status).in_(["onhold", "on_hold"]))
        else:
            query = query.filter(func.lower(JobApplication.status) == status_lower)

    # Filter by apply mode
    if apply_mode:
        query = query.filter(func.lower(JobApplication.apply_mode) == apply_mode.lower())

    # Filter by job title or company name search
    if search:
        query = query.join(Company, JobPosting.company_id == Company.id).filter(
            or_(
                JobPosting.title.ilike(f"%{search}%"),
                Company.name.ilike(f"%{search}%")
            )
        )

    # Filter by work type (Remote, Hybrid, Onsite)
    if work_type and work_type.lower() != "all":
        query = query.filter(JobPosting.work_mode.has(name=work_type.upper()))

    # Filter by job type (Full-Time, Internship, Contract)
    if job_type and job_type.lower() != "all":
        norm_jt = job_type.replace("-", "_").replace(" ", "_").upper()
        query = query.filter(JobPosting.employment_type.has(name=norm_jt))

    # Filter by location (country)
    if location and location.lower() != "all":
        if location.lower() in ("u.s.", "us", "united states"):
            query = query.filter(JobPosting.country.has(iso_code="US"))
        elif location.lower() in ("india", "in"):
            query = query.filter(JobPosting.country.has(iso_code="IN"))

    # Filter by visa sponsorship
    if visa_sponsorship and visa_sponsorship.lower() != "all":
        if visa_sponsorship.lower() == "h1b sponsorship":
            query = query.filter(JobPosting.visa_status.has(name="H-1B Visa"))
        elif visa_sponsorship.lower() == "sponsorship available":
            query = query.filter(or_(JobPosting.requires_visa_sponsorship.isnot(None), JobPosting.must_be_authorized_to_work == False))
        elif visa_sponsorship.lower() == "no sponsorship":
            query = query.filter(JobPosting.requires_visa_sponsorship.is_(None))

    # Filter by salary range
    if salary_min is not None:
        query = query.filter(JobPosting.salary_min >= salary_min)
    if salary_max is not None:
        query = query.filter(JobPosting.salary_max <= salary_max)

    # Filter by job post date
    if job_post_date:
        now = datetime.now(timezone.utc)
        if job_post_date.lower() == "today" or job_post_date.lower() == "within 24 hour" or job_post_date.lower() == "within 24 hours":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=1))
        elif job_post_date.lower() == "last 7 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=7))
        elif job_post_date.lower() == "last 30 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=30))

    # Apply database-level pagination only if match_score filter is NOT applied
    is_match_score_filtered = match_score and match_score.lower() != "all"
    
    query = query.order_by(JobApplication.created_at.desc())
    if not is_match_score_filtered:
        query = query.offset(skip).limit(limit)

    # Fetch matching applications
    apps = query.all()
    
    matching_service = MatchingEngine(db)
    response = []
    
    for record in apps:
        job = record.job
        if not job:
            continue
            
        # Get resume used for this job
        resume = db.query(Resume).filter(Resume.candidate_id == candidate.id, Resume.job_id == job.id).first()
        if not resume:
            resume = primary_resume
            
        # Calculate AI match score
        ai_score = 0
        if resume and resume.overall_embedding is not None:
            try:
                score_details = matching_service.score_resume_for_job(resume.id, job.id)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
                
        # Filter by Match Score in Python if specified
        if is_match_score_filtered:
            norm_score = match_score.replace(" ", "").replace("–", "-").replace("—", "-")
            if norm_score == "90%+" and ai_score < 90:
                continue
            elif norm_score == "80-89%" and not (80 <= ai_score <= 89):
                continue
            elif norm_score == "70-79%" and not (70 <= ai_score <= 79):
                continue
            elif norm_score == "Below 70%" and ai_score >= 70:
                continue
            elif "below70" in norm_score.lower() and ai_score >= 70:
                continue
                
        # Build Location Label: e.g. "San Francisco, CA (Hybrid)"
        work_mode_str = job.work_mode.name.title() if job.work_mode else None
        location_parts = []
        if job.city:
            location_parts.append(job.city.name)
        if job.state:
            state_part = job.state.code or job.state.name
            location_parts.append(state_part)
            
        base_loc = ", ".join(location_parts) if location_parts else None
        if base_loc and work_mode_str:
            location_label = f"{base_loc} ({work_mode_str})"
        elif work_mode_str:
            location_label = work_mode_str
        elif base_loc:
            location_label = base_loc
        else:
            location_label = "Remote"
            
        # Mapped Status Label
        status_lower = record.status.lower()
        if status_lower == "applied":
            status_label = "Applied"
        elif status_lower == "under_review":
            status_label = "Under Review"
        elif status_lower == "shortlisted":
            status_label = "Shortlisted"
        elif status_lower in ("interviewing", "interviewed", "interview"):
            status_label = "Interviewing"
        elif status_lower in ("onhold", "on_hold"):
            status_label = "On Hold"
        elif status_lower == "offered":
            status_label = "Offer Received"
        elif status_lower == "hired":
            status_label = "Hired"
        elif status_lower == "rejected":
            status_label = "Rejected"
        else:
            status_label = record.status.title()
            
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None

        response.append(
            JobApplicationResponse(
                id=record.id,
                job_id=record.job_id,
                job_title=job.title,
                company_name=job.company.name if job.company else None,
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company and job.company.logo_url else None,
                status=record.status,
                apply_mode=record.apply_mode,
                applied_at=record.created_at,
                match_score=ai_score,
                location_label=location_label,
                status_label=status_label,
                experience_min_years=job.min_experience_years,
                experience_max_years=job.max_experience_years,
                experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
                salary_min=job.salary_min * 12 if job.salary_min is not None else None,
                salary_max=job.salary_max * 12 if job.salary_max is not None else None,
                salary_currency_code=currency_code,
                salary_currency_symbol=currency_symbol,
                salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code)
            )
        )

    # Apply Python-level pagination if match_score filter was applied
    if is_match_score_filtered:
        return response[skip : skip + limit]

    return response


@router.get("/applications/stats", response_model=JobApplicationStatsResponse)
def get_job_application_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
) -> JobApplicationStatsResponse:
    """
    Get job application stats based on status for the current candidate.
    """
    candidate = get_candidate(current_user, db)
    
    stats_query = (
        db.query(JobApplication.status, func.count(JobApplication.id))
        .filter(JobApplication.candidate_id == candidate.id)
        .group_by(JobApplication.status)
        .all()
    )
    
    stats_data = {
        "applied": 0,
        "under_review": 0,
        "shortlisted": 0,
        "interviewing": 0,
        "on_hold": 0,
        "offered": 0,
        "hired": 0,
        "rejected": 0,
        "total": 0
    }
    
    for status_str, count in stats_query:
        if not status_str:
            continue
        status_lower = status_str.lower()
        if status_lower == "applied":
            stats_data["applied"] += count
        elif status_lower == "under_review":
            stats_data["under_review"] += count
        elif status_lower == "shortlisted":
            stats_data["shortlisted"] += count
        elif status_lower in ("interviewing", "interviewed", "interview"):
            stats_data["interviewing"] += count
        elif status_lower in ("onhold", "on_hold"):
            stats_data["on_hold"] += count
        elif status_lower == "offered":
            stats_data["offered"] += count
        elif status_lower == "hired":
            stats_data["hired"] += count
        elif status_lower == "rejected":
            stats_data["rejected"] += count
        
        stats_data["total"] += count
        
    return JobApplicationStatsResponse(**stats_data)


@router.get("/jobs/{job_id}/application", response_model=JobPosterApplicantProfileResponse)
def get_job_seeker_application_details(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
) -> JobPosterApplicantProfileResponse:
    """
    Get the detailed candidate application for a specific job posting,
    including the resume used while applying, the cover letter, summary, and timeline.
    """
    candidate = get_candidate(current_user, db)

    # Verify the application exists
    app = db.query(JobApplication).filter(
        JobApplication.job_id == job_id,
        JobApplication.candidate_id == candidate.id
    ).first()

    if not app:
        raise HTTPException(
            status_code=404,
            detail="Application on this job was not found."
        )

    # Fetch job posting
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.is_active == True
    ).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job posting not found."
        )

    # Resolve the resume used (job-specific or primary)
    resume = db.query(Resume).options(
        joinedload(Resume.sections)
    ).filter(
        Resume.candidate_id == candidate.id,
        Resume.job_id == job_id
    ).first()
    
    if not resume:
        resume = db.query(Resume).options(
            joinedload(Resume.sections)
        ).filter(
            Resume.candidate_id == candidate.id,
            Resume.is_primary == True
        ).first()

    # Calculate AI match score
    ai_score = 0
    if resume and resume.overall_embedding is not None:
        try:
            matching_service = MatchingEngine(db)
            score_details = matching_service.score_resume_for_job(resume.id, job_id)
            ai_score = int(score_details["final_score"])
        except Exception:
            ai_score = 0

    # Extract summary section content from resume
    about_summary = None
    if resume:
        summary_section = next((s for s in resume.sections if s.section_type == "Summary"), None)
        if summary_section:
            about_summary = summary_section.optimized_content or summary_section.original_content

    # Format salary range label if candidate specifies pref_min_salary
    salary_range_label = None
    if candidate.pref_min_salary is not None:
        min_salary_k = candidate.pref_min_salary // 1000
        salary_range_label = f"${min_salary_k}k - ${min_salary_k + 10}k /month"

    # Construct the timeline dynamically
    app_status = app.status.lower()
    
    # 1. View Details (always completed)
    timeline = [
        TimelineEvent(
            title="View Details",
            status="completed",
            updated_at=app.created_at
        )
    ]
    
    # Helper to check completion
    def get_stage_status(completed_statuses: list, active_statuses: list) -> str:
        if app_status in completed_statuses:
            return "completed"
        if app_status in active_statuses:
            return "active"
        return "pending"

    # 2. Inreview for Next Stage
    inreview_completed = ["under_review", "shortlisted", "interviewing", "interviewed", "offered", "hired"]
    inreview_active = ["applied"]
    timeline.append(
        TimelineEvent(
            title="Inreview for Next Stage",
            status=get_stage_status(inreview_completed, inreview_active),
            updated_at=app.updated_at if app_status in inreview_completed else None
        )
    )

    # 3. Candidate Shortlisted!
    shortlist_completed = ["shortlisted", "interviewing", "interviewed", "offered", "hired"]
    shortlist_active = ["under_review"]
    timeline.append(
        TimelineEvent(
            title="Candidate Shortlisted!",
            status=get_stage_status(shortlist_completed, shortlist_active),
            updated_at=app.updated_at if app_status in shortlist_completed else None
        )
    )

    # 4. Application successful (Candidate Selected!)
    success_completed = ["offered", "hired"]
    success_active = ["interviewing", "interviewed"]
    timeline.append(
        TimelineEvent(
            title="Application successful",
            status=get_stage_status(success_completed, success_active),
            updated_at=app.updated_at if app_status in success_completed else None
        )
    )

    # If the application is rejected or onhold
    if app_status == "rejected":
        timeline.append(
            TimelineEvent(
                title="Application Rejected",
                status="completed",
                updated_at=app.updated_at
            )
        )
    elif app_status in ("onhold", "on_hold"):
        timeline.append(
            TimelineEvent(
                title="Application On Hold",
                status="completed",
                updated_at=app.updated_at
            )
        )

    # Prepare response
    return JobPosterApplicantProfileResponse(
        id=candidate.id,
        full_name=candidate.full_name,
        email=candidate.user.email if candidate.user else "",
        phone=candidate.phone,
        profile_picture=s3_service.get_presigned_url(candidate.profile_picture) if candidate.profile_picture else None,
        is_verified=candidate.user.is_verified if candidate.user else False,
        role=candidate.taxonomy_domain.name if candidate.taxonomy_domain else None,
        ai_score=ai_score,
        experience_years=resume.total_experience_years if resume else 0,
        salary_range_label=salary_range_label,
        employment_type=candidate.pref_role_type,
        preferred_location=candidate.pref_locations,
        status=app.status,
        about_summary=about_summary,
        resume_file_name=resume.file_name if resume else None,
        resume_file_url=s3_service.get_presigned_url(resume.file_url) if resume else None,
        cover_letter=s3_service.get_presigned_url(app.cover_letter) if app.cover_letter else None,
        timeline=timeline,
        is_viewed=app.is_viewed
    )


def format_resume_structure(resume: Resume, candidate: Candidate, user: User) -> Dict[str, Any]:
    structured_data = resume.structured_data
    if not structured_data:
        summary_sec = next((s for s in resume.sections if s.section_type == "Summary"), None)
        skills_sec = next((s for s in resume.sections if s.section_type == "Skills"), None)
        experience_sec = next((s for s in resume.sections if s.section_type == "Experience"), None)
        education_sec = next((s for s in resume.sections if s.section_type == "Education"), None)
        projects_sec = next((s for s in resume.sections if s.section_type == "Projects"), None)
        certifications_sec = next((s for s in resume.sections if s.section_type == "Certifications"), None)
        
        structured_data = {
            "personalInfo": {
                "fullName": candidate.full_name,
                "email": user.email,
                "phone": candidate.phone,
                "location": candidate.current_address,
                "linkedin": candidate.linkedin_url,
                "github": None,
                "portfolio": candidate.portfolio_url
            },
            "summary": {
                "text": (summary_sec.optimized_content or summary_sec.original_content) if summary_sec else candidate.about_summary
            },
            "skills": {
                "technical": resume.extracted_skills or [],
                "soft": [],
                "tools": []
            },
            "experience": [
                {
                    "id": "exp_1",
                    "company": "N/A",
                    "role": "N/A",
                    "location": None,
                    "employmentType": None,
                    "startDate": None,
                    "endDate": None,
                    "isCurrent": False,
                    "bullets": [experience_sec.optimized_content or experience_sec.original_content] if experience_sec else []
                }
            ] if experience_sec else [],
            "education": [
                {
                    "id": "edu_1",
                    "institution": "N/A",
                    "degree": "N/A",
                    "location": None,
                    "startDate": None,
                    "endDate": None,
                    "grade": None,
                    "isCurrent": False
                }
            ] if education_sec else [],
            "projects": [
                {
                    "id": "proj_1",
                    "title": "Project",
                    "description": projects_sec.optimized_content or projects_sec.original_content if projects_sec else None,
                    "techStack": [],
                    "link": None,
                    "startDate": None,
                    "endDate": None,
                    "bullets": []
                }
            ] if projects_sec else [],
            "certifications": [
                {
                    "id": "cert_1",
                    "title": certifications_sec.optimized_content or certifications_sec.original_content if certifications_sec else None,
                    "issuer": "N/A",
                    "issueDate": None,
                    "expiryDate": None,
                    "credentialUrl": None
                }
            ] if certifications_sec else [],
            "achievements": [],
            "languages": [],
            "customSections": []
        }

    # Dynamically inject/overwrite properties to ensure they match current DB state
    structured_data["resumeId"] = str(resume.id)
    structured_data["userId"] = str(user.id)
    structured_data["template"] = "template_1"
    
    # Overwrite profile image with S3 presigned URL
    if "personalInfo" in structured_data:
        structured_data["personalInfo"]["profileImage"] = s3_service.get_presigned_url(candidate.profile_picture) if candidate.profile_picture else None
        
        # Ensure email, phone, location, full_name, linkedin, portfolio are populated from candidate table if missing
        if not structured_data["personalInfo"].get("fullName"):
            structured_data["personalInfo"]["fullName"] = candidate.full_name
        if not structured_data["personalInfo"].get("email"):
            structured_data["personalInfo"]["email"] = user.email
        if not structured_data["personalInfo"].get("phone"):
            structured_data["personalInfo"]["phone"] = candidate.phone
        if not structured_data["personalInfo"].get("location"):
            structured_data["personalInfo"]["location"] = candidate.current_address
        if not structured_data["personalInfo"].get("linkedin"):
            structured_data["personalInfo"]["linkedin"] = candidate.linkedin_url
        if not structured_data["personalInfo"].get("portfolio"):
            structured_data["personalInfo"]["portfolio"] = candidate.portfolio_url

    # Add metadata
    structured_data["meta"] = {
        "createdAt": resume.created_at.isoformat() if resume.created_at else None,
        "updatedAt": resume.updated_at.isoformat() if resume.updated_at else None,
        "version": resume.version_number
    }

    return structured_data


def update_structured_data_with_optimized_sections(structured_data: Dict[str, Any], sections: List[ResumeSection]) -> Dict[str, Any]:
    if not structured_data:
        return structured_data
        
    import copy
    import re
    sd = copy.deepcopy(structured_data)
    
    for sec in sections:
        content = sec.optimized_content or sec.original_content
        if not content:
            continue
            
        s_type = sec.section_type
        if s_type == "Summary":
            if "summary" not in sd:
                sd["summary"] = {}
            sd["summary"]["text"] = content
            
        elif s_type == "Skills":
            skills_list = [s.strip() for s in re.split(r'[,\n•*-]+', content) if s.strip()]
            if "skills" not in sd:
                sd["skills"] = {"technical": [], "soft": [], "tools": []}
            sd["skills"]["technical"] = list(set(sd["skills"].get("technical", []) + skills_list))
            
        elif s_type == "Experience":
            bullets = []
            for line in content.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                cleaned = re.sub(r'^([•\-*\d\.\s]+)', '', line_str).strip()
                if cleaned:
                    bullets.append(cleaned)
            
            if "experience" in sd and isinstance(sd["experience"], list) and len(sd["experience"]) > 0:
                sd["experience"][0]["bullets"] = bullets
                
        elif s_type == "Projects":
            bullets = []
            for line in content.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                cleaned = re.sub(r'^([•\-*\d\.\s]+)', '', line_str).strip()
                if cleaned:
                    bullets.append(cleaned)
            if "projects" in sd and isinstance(sd["projects"], list) and len(sd["projects"]) > 0:
                sd["projects"][0]["bullets"] = bullets
                
    return sd


@router.post("/jobs/{job_id}/optimize-resume")
def optimize_resume_for_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    # Enforce limit for Free Plan resume optimization limit
    if limits["monthly_resume_optimization_limit"] < 9999:
        if candidate.resume_optimizations_used_this_month >= limits["monthly_resume_optimization_limit"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"You have reached your monthly Resume Optimization limit of {limits['monthly_resume_optimization_limit']}."
            )
            
    # Get primary resume
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    if not primary_resume:
        raise HTTPException(status_code=400, detail="You do not have a primary resume uploaded.")

    # Check if an active optimized resume already exists for this job
    existing_optimized_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.job_id == job.id,
        Resume.is_deleted == False
    ).first()

    # Check saved resumes limit (only if creating a new one)
    if not existing_optimized_resume:
        existing_non_deleted_count = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.is_deleted == False
        ).count()
        if existing_non_deleted_count >= limits["saved_resumes_limit"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You have reached your limit of {limits['saved_resumes_limit']} saved resumes. Please delete an existing resume to optimize a new one."
            )
            
    # Check and deduct credits via CreditManager (Cost: 10 AI credits)
    credit_manager.check_and_deduct_credits(
        candidate=candidate,
        cost=CreditManager.COST_RESUME_OPTIMIZATION,
        limits=limits,
        db=db
    )
            
    # Union of skills so the matching engine score goes up for the target job as intended
    union_skills = list(set(primary_resume.extracted_skills or []) | set(job.extracted_skills or []))
    
    if existing_optimized_resume:
        resume_to_use = existing_optimized_resume
        resume_to_use.file_url = primary_resume.file_url
        resume_to_use.total_experience_years = primary_resume.total_experience_years
        resume_to_use.taxonomy_domain_id = primary_resume.taxonomy_domain_id
        resume_to_use.extracted_skills = union_skills
        resume_to_use.structured_data = primary_resume.structured_data
        db.add(resume_to_use)
        db.flush()
        
        # Update/Create sections
        new_sections = []
        existing_sections_by_type = {s.section_type: s for s in resume_to_use.sections}
        primary_section_types = {s.section_type for s in primary_resume.sections}
        
        # Delete any sections in existing optimized resume that are no longer in primary resume
        for s_type, s in list(existing_sections_by_type.items()):
            if s_type not in primary_section_types:
                db.delete(s)
                
        for section in primary_resume.sections:
            result = optimization_engine.optimize_section(job, section)
            
            existing_sec = existing_sections_by_type.get(section.section_type)
            if existing_sec:
                existing_sec.original_content = section.original_content
                existing_sec.optimized_content = result.get("optimized_content")
                existing_sec.optimization_metadata = {
                    "missing_keywords": result.get("missing_keywords", []),
                    "feedback": result.get("optimization_feedback", "")
                }
                db.add(existing_sec)
                new_sections.append(existing_sec)
            else:
                new_section = ResumeSection(
                    resume_id=resume_to_use.id,
                    section_type=section.section_type,
                    original_content=section.original_content,
                    optimized_content=result.get("optimized_content"),
                    optimization_metadata={
                        "missing_keywords": result.get("missing_keywords", []),
                        "feedback": result.get("optimization_feedback", "")
                    }
                )
                db.add(new_section)
                new_sections.append(new_section)
        db.flush()
    else:
        # Create new optimized resume version
        existing_resumes_count = db.query(Resume).filter(Resume.candidate_id == candidate.id).count()
        resume_to_use = Resume(
            candidate_id=candidate.id,
            file_url=primary_resume.file_url,
            file_name=f"Optimized Resume - {job.title}",
            parent_resume_id=primary_resume.id,
            job_id=job.id,
            version_number=existing_resumes_count + 1,
            is_primary=False,
            is_ai_optimized=True,
            total_experience_years=primary_resume.total_experience_years,
            taxonomy_domain_id=primary_resume.taxonomy_domain_id,
            extracted_skills=union_skills,
            structured_data=primary_resume.structured_data
        )
        db.add(resume_to_use)
        db.flush()
        
        # Optimize resume sections
        new_sections = []
        for section in primary_resume.sections:
            result = optimization_engine.optimize_section(job, section)
            
            new_section = ResumeSection(
                resume_id=resume_to_use.id,
                section_type=section.section_type,
                original_content=section.original_content,
                optimized_content=result.get("optimized_content"),
                optimization_metadata={
                    "missing_keywords": result.get("missing_keywords", []),
                    "feedback": result.get("optimization_feedback", "")
                }
            )
            db.add(new_section)
            new_sections.append(new_section)
        db.flush()
        
    # Update structured_data using the optimized sections
    from sqlalchemy.orm.attributes import flag_modified
    resume_to_use.structured_data = update_structured_data_with_optimized_sections(resume_to_use.structured_data, new_sections)
    flag_modified(resume_to_use, "structured_data")
        
    # Increment usage
    candidate.resume_optimizations_used_this_month += 1
    db.add(candidate)
    db.commit()
    db.refresh(resume_to_use)
    
    return format_resume_structure(resume_to_use, candidate, current_user)


@router.post("/resume/optimize")
def optimize_resume_general(
    resume_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Optimize a specific resume generally (without a target job description).
    """
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    # Enforce limit for Free Plan resume optimization limit
    if limits["monthly_resume_optimization_limit"] < 9999:
        if candidate.resume_optimizations_used_this_month >= limits["monthly_resume_optimization_limit"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"You have reached your monthly Resume Optimization limit of {limits['monthly_resume_optimization_limit']}."
            )
            
    # Check saved resumes limit
    existing_non_deleted_count = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_deleted == False
    ).count()
    if existing_non_deleted_count >= limits["saved_resumes_limit"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You have reached your limit of {limits['saved_resumes_limit']} saved resumes. Please delete an existing resume to optimize a new one."
        )
            
    # Check and deduct credits via CreditManager (Cost: 10 AI credits)
    credit_manager.check_and_deduct_credits(
        candidate=candidate,
        cost=CreditManager.COST_RESUME_OPTIMIZATION,
        limits=limits,
        db=db
    )
            
    # Get specific resume
    primary_resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.candidate_id == candidate.id
    ).first()
    if not primary_resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
        
    existing_resumes_count = db.query(Resume).filter(Resume.candidate_id == candidate.id).count()
    
    # Create new optimized resume version
    new_resume = Resume(
        candidate_id=candidate.id,
        file_url=primary_resume.file_url,
        file_name="Optimized Resume - General",
        parent_resume_id=primary_resume.id,
        job_id=None,
        version_number=existing_resumes_count + 1,
        is_primary=False,
        is_ai_optimized=True,
        total_experience_years=primary_resume.total_experience_years,
        taxonomy_domain_id=primary_resume.taxonomy_domain_id,
        extracted_skills=primary_resume.extracted_skills,
        structured_data=primary_resume.structured_data
    )
    db.add(new_resume)
    db.flush() # Populate new_resume.id
    
    # Optimize resume sections
    new_sections = []
    for section in primary_resume.sections:
        result = optimization_engine.optimize_section_general(section)
        
        # Save optimized content in a new section record linked to the new resume version
        new_section = ResumeSection(
            resume_id=new_resume.id,
            section_type=section.section_type,
            original_content=section.original_content,
            optimized_content=result.get("optimized_content"),
            optimization_metadata={
                "feedback": result.get("optimization_feedback", "")
            }
        )
        db.add(new_section)
        new_sections.append(new_section)
        
    # Update new resume's structured_data using the optimized sections
    from sqlalchemy.orm.attributes import flag_modified
    new_resume.structured_data = update_structured_data_with_optimized_sections(new_resume.structured_data, new_sections)
    flag_modified(new_resume, "structured_data")
        
    # Increment usage
    candidate.resume_optimizations_used_this_month += 1
    db.add(candidate)
    db.commit()
    db.refresh(new_resume)
    
    return format_resume_structure(new_resume, candidate, current_user)


@router.post("/resumes/{resume_id}/sections/{section_type}/optimize", response_model=OptimizeSectionResult)
def optimize_resume_section(
    resume_id: UUID,
    section_type: SectionType,
    payload: OptimizeSectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Optimize a specific section of a resume.
    If job_id is passed, optimizes against the job description; otherwise, performs a general polish.
    """
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    # 1. Fetch the resume and ensure it belongs to the candidate
    resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.candidate_id == candidate.id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
        
    # 2. Find the specific section
    section = db.query(ResumeSection).filter(
        ResumeSection.resume_id == resume.id,
        ResumeSection.section_type == section_type.value
    ).first()
    if not section:
        raise HTTPException(
            status_code=404,
            detail=f"Section '{section_type.value}' not found in this resume."
        )
        
    # 3. Check credits (Section-wise optimization costs 2 AI credits)
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    credit_manager.check_and_deduct_credits(
        candidate=candidate,
        cost=CreditManager.COST_SECTION_OPTIMIZATION,
        limits=limits,
        db=db
    )
    
    # 4. Optimize the section based on whether job_id is passed
    if payload.job_id:
        job = db.query(JobPosting).filter(
            JobPosting.id == payload.job_id,
            JobPosting.is_active == True
        ).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job posting not found.")
            
        result = optimization_engine.optimize_section(job, section)
        
        # Save optimized content back to the section
        section.optimized_content = result.get("optimized_content")
        section.optimization_metadata = {
            "missing_keywords": result.get("missing_keywords", []),
            "feedback": result.get("optimization_feedback", "")
        }
    else:
        result = optimization_engine.optimize_section_general(section)
        
        # Save optimized content back to the section
        section.optimized_content = result.get("optimized_content")
        section.optimization_metadata = {
            "feedback": result.get("optimization_feedback", "")
        }
        
    db.add(section)
    db.commit()
    db.refresh(section)
    
    return OptimizeSectionResult(
        section_type=section.section_type,
        original_content=section.original_content,
        optimized_content=section.optimized_content,
        optimization_feedback=section.optimization_metadata.get("feedback") if section.optimization_metadata else None
    )


@router.post("/jobs/{job_id}/generate-cover-letter", response_model=CoverLetterResponse)
def generate_cover_letter_for_job(
    job_id: UUID,
    payload: CoverLetterGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    # Enforce limit for Free Plan cover letter limit
    if limits["monthly_cover_letter_limit"] < 9999:
        if limits["monthly_cover_letter_limit"] == 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="The Free plan only supports manual upload of cover letters. Please upgrade to a paid plan to use AI generation."
            )
        elif candidate.cover_letters_generated_this_month >= limits["monthly_cover_letter_limit"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"You have reached your monthly Cover Letter Generation limit of {limits['monthly_cover_letter_limit']}."
            )
            
    # Check and deduct credits via CreditManager (Cost: 3 AI credits)
    credit_manager.check_and_deduct_credits(
        candidate=candidate,
        cost=CreditManager.COST_COVER_LETTER_GENERATION,
        limits=limits,
        db=db
    )
            
    # Get primary resume summary section
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    if not primary_resume:
        raise HTTPException(status_code=400, detail="You do not have a primary resume uploaded.")
        
    resume_skills = ", ".join(primary_resume.extracted_skills) if primary_resume.extracted_skills else "None"
    
    # Call Gemini to generate cover letter
    import google.generativeai as genai
    from app.core.config import settings
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    company_name = job.company.name if job.company else "Target Company"
    company_desc = job.company.description if (job.company and job.company.description) else "A leading innovator in the industry."
    job_overview = job.job_overview or job.description or ""
    about_role = job.about_role or ""
    requirements_str = "\n".join(f"- {r}" for r in job.requirements) if (job.requirements and isinstance(job.requirements, list)) else ""
    responsibilities_str = "\n".join(f"- {r}" for r in job.responsibilities) if (job.responsibilities and isinstance(job.responsibilities, list)) else ""
    work_mode_str = job.work_mode.name if job.work_mode else "Not specified"
    total_exp = f"{primary_resume.total_experience_years} years" if primary_resume.total_experience_years else "Not specified"

    customization_instruction = ""
    if payload and payload.customization:
        custom_lower = payload.customization.strip().lower()
        if custom_lower == "shorten":
            customization_instruction = "Make the cover letter extremely concise, limited to 2 short paragraphs max."
        elif custom_lower in ("improve_tone", "improve tone"):
            customization_instruction = "Polishing instructions: Ensure the tone is highly professional, warm, engaging, and confident."
        elif custom_lower in ("more_technical", "more technical"):
            customization_instruction = "Highlighting instructions: Emphasize technical skills, technical architectures, and specific technologies/tools matching the candidate's profile."
        elif custom_lower in ("ats_optimize", "ats optimize"):
            customization_instruction = "ATS optimization instructions: Focus on weaving in exact industry keywords, core requirements, and phrases from the job description to optimize search relevance."
        else:
            customization_instruction = f"Additional User Instruction: {payload.customization}"

    prompt = f"""
    You are an expert career assistant. Generate a highly professional, compelling, and customized cover letter for:
    
    --- TARGET COMPANY ---
    Name: {company_name}
    About Company: {company_desc}
    
    --- JOB POSITION ---
    Title: {job.title}
    Work Mode: {work_mode_str}
    Job Overview: {job_overview}
    About the Role: {about_role}
    
    Requirements:
    {requirements_str}
    
    Responsibilities:
    {responsibilities_str}
    
    --- CANDIDATE PROFILE ---
    Name: {candidate.full_name}
    Total Experience: {total_exp}
    Skills: {resume_skills}
    
    {customization_instruction}
    
    Generate a cover letter customized to match the candidate's skills and experience to the target company's business domain and the job's responsibilities/requirements. 
    The tone should be professional, warm, confident, and highly tailored. Avoid generic platitudes. Output only the cover letter body.
    """
    
    try:
        response = model.generate_content(prompt)
        cover_letter_text = response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate cover letter with Gemini: {e}")
        
    # Create a new CoverLetter record in the database
    new_cover_letter = CoverLetter(
        candidate_id=candidate.id,
        job_id=job.id,
        title=f"{job.title} Cover Letter",
        content=cover_letter_text,
        is_default=False
    )
    db.add(new_cover_letter)
        
    # Increment usage
    candidate.cover_letters_generated_this_month += 1
    db.add(candidate)

    db.commit()
    
    return CoverLetterResponse(cover_letter=cover_letter_text)

@router.get("/jobs/{job_id}/analyze-fit", response_model=FitAnalysisResponse)
def analyze_fit_for_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    if not primary_resume:
        raise HTTPException(status_code=400, detail="You do not have a primary resume uploaded.")
        
    # Score resume
    matching_service = MatchingEngine(db)
    score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
    
    breakdown = score_details["breakdown"]
    insights = score_details["insights"]
    
    # Dynamic missing skills check based on plan permissions
    plan_tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(plan_tier, PLAN_LIMITS["free"])
    
    missing_skills = []
    if limits["missing_skills_analysis_enabled"]:
        missing_skills = insights.get("missing_skills", [])
        
    return FitAnalysisResponse(
        final_score=int(score_details["final_score"]),
        experience_match_percent=int(breakdown.get("experience", 0)),
        skill_match_percent=int(breakdown.get("skills", 0)),
        industry_fit_percent=int(breakdown.get("logistics", 0)),
        resume_alignment_percent=int(breakdown.get("semantic", 0)),
        matching_skills=insights.get("matched_skills", []),
        missing_keywords=missing_skills
    )
# --- SAVED RESUMES MANAGEMENT ---

@router.get("/resumes", response_model=PaginatedResumeVersionResponse)
def list_resumes(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """List all saved resume versions for the candidate."""
    candidate = get_candidate(current_user, db)
    resumes = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_deleted == False
    ).order_by(Resume.is_primary.desc(), Resume.version_number.desc()).all()
    
    response = []
    matching_service = MatchingEngine(db)
    for r in resumes:
        job_title = None
        company_name = None
        ai_score = None
        if r.job_id:
            job = db.query(JobPosting).filter(JobPosting.id == r.job_id).first()
            if job:
                job_title = job.title
                company_name = job.company.name if job.company else None
                try:
                    score_details = matching_service.score_resume_for_job(r.id, job.id)
                    ai_score = int(score_details["final_score"])
                except Exception:
                    ai_score = None
                    
        response.append(
            ResumeVersionResponse(
                id=r.id,
                file_name=r.file_name,
                file_url=s3_service.get_presigned_url(r.file_url),
                version_number=r.version_number,
                is_primary=r.is_primary,
                is_ai_optimized=r.is_ai_optimized,
                created_at=r.created_at,
                job_id=r.job_id,
                job_title=job_title,
                company_name=company_name,
                ai_score=ai_score
            )
        )
    return {"resumes": response[skip : skip + limit], "count": len(response)}
 
 
@router.get("/resumes/{resume_id}/structure")
def get_resume_structure(
    resume_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
) -> Dict[str, Any]:
    """
    Fetch the detailed extracted structured data (total experience, skills,
    domain, and sections) of a specific uploaded resume formatted for the frontend.
    """
    candidate = get_candidate(current_user, db)
    
    resume = db.query(Resume).options(
        joinedload(Resume.sections),
        joinedload(Resume.taxonomy_domain)
    ).filter(
        Resume.id == resume_id,
        Resume.candidate_id == candidate.id,
        Resume.is_deleted == False
    ).first()
    
    if not resume:
        raise HTTPException(
            status_code=404,
            detail="Resume not found."
        )
        
    return format_resume_structure(resume, candidate, current_user)


@router.post("/resumes/{resume_id}/analyze-fit", response_model=ResumeAnalyzeFitResponse)
def analyze_resume_fit_endpoint(
    resume_id: UUID,
    payload: ResumeAnalyzeFitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Analyzes a specific resume against a job description, returning
    the match score, status, gaps, and strengths based on embedding similarity.
    """
    import numpy as np
    candidate = get_candidate(current_user, db)
    
    # 1. Fetch the resume and check ownership
    resume = db.query(Resume).options(joinedload(Resume.sections)).filter(
        Resume.id == resume_id,
        Resume.candidate_id == candidate.id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
        
    # 2. Get the resume content for LLM processing
    sections = resume.sections
    if not sections:
        resume_content = json.dumps(resume.structured_data) if resume.structured_data else ""
    else:
        sections_texts = []
        for sec in sections:
            content = sec.optimized_content or sec.original_content
            if content:
                sections_texts.append(f"[{sec.section_type}]\n{content}")
        resume_content = "\n\n".join(sections_texts)
        
    if not resume_content.strip():
        resume_content = resume.file_name or "Resume"

    # 3. Fetch the JobPosting from the database
    job = db.query(JobPosting).filter(JobPosting.id == payload.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    # Auto-generate job embedding if it is missing
    if job.embedding is None:
        description = job.description or ""
        if not description.strip() and job.job_overview:
            description = job.job_overview
        job.embedding = embedding_service.get_embedding(description)
        db.add(job)
        db.commit()
        
    job_description = job.description or ""
    if not job_description.strip() and job.job_overview:
        job_description = job.job_overview

    # Calculate embedding-based match score
    job_desc_embedding = job.embedding
    
    # Auto-generate resume embedding if it is missing
    if resume.overall_embedding is None:
        parts = []
        if resume.extracted_skills:
            parts.append(" ".join(resume.extracted_skills))
        for sec in sections:
            content = sec.optimized_content or sec.original_content
            if content:
                parts.append(content)
        resume_text = " ".join(parts)
        if not resume_text.strip():
            resume_text = resume.file_name or "Resume"
        resume.overall_embedding = embedding_service.get_embedding(resume_text)
        db.add(resume)
        db.commit()

    vec1 = np.array(job_desc_embedding)
    vec2 = np.array(resume.overall_embedding)
    
    dot_product = np.dot(vec1, vec2)
    norm_v1 = np.linalg.norm(vec1)
    norm_v2 = np.linalg.norm(vec2)
    
    if norm_v1 == 0 or norm_v2 == 0:
        similarity = 0.0
    else:
        similarity = float(dot_product / (norm_v1 * norm_v2))
        
    # Use direct similarity percentage without calibrating to 0
    score = int(similarity * 100)
        
    # 4. Call the Gemini optimization/matching engine to analyze fit
    analysis = optimization_engine.analyze_resume_fit(resume_content, job_description, score)
    
    if "error" in analysis:
        raise HTTPException(status_code=500, detail=analysis["status_message"])
        
    return ResumeAnalyzeFitResponse(
        score=analysis["score"],
        match_status=analysis["match_status"],
        status_message=analysis["status_message"],
        gaps=analysis["gaps"],
        strengths=analysis["strengths"]
    )


@router.get("/resumes/{resume_id}/suggestions", response_model=ResumeSuggestionsResponse)
def get_resume_suggestions_endpoint(
    resume_id: UUID,
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Returns missing keywords and AI suggestions for a given resume version
    compared against a job posting, dynamically updated with resume optimization.
    """
    candidate = get_candidate(current_user, db)
    
    # 1. Fetch the resume and check candidate ownership
    resume = db.query(Resume).options(joinedload(Resume.sections)).filter(
        Resume.id == resume_id,
        Resume.candidate_id == candidate.id
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
        
    # 2. Fetch the target JobPosting
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    # 3. Reconstruct the current resume content using optimized_content where available
    sections = resume.sections
    sections_texts = []
    has_optimized_summary = False
    has_optimized_skills = False
    has_optimized_experience = False
    has_optimized_certifications = False
    
    for sec in sections:
        content = sec.optimized_content or sec.original_content
        if content:
            sections_texts.append(f"[{sec.section_type}]\n{content}")
            
        if sec.section_type == SectionType.SUMMARY.value and sec.optimized_content:
            has_optimized_summary = True
        elif sec.section_type == SectionType.SKILLS.value and sec.optimized_content:
            has_optimized_skills = True
        elif sec.section_type == SectionType.EXPERIENCE.value and sec.optimized_content:
            has_optimized_experience = True
        elif sec.section_type == SectionType.CERTIFICATIONS.value and sec.optimized_content:
            has_optimized_certifications = True
            
    resume_content = "\n\n".join(sections_texts)
    if not resume_content.strip():
        resume_content = resume.file_name or "Resume"
        
    # 4. Call the Gemini optimization/matching engine to generate suggestions
    job_description = job.description or ""
    if not job_description.strip() and job.job_overview:
        job_description = job.job_overview
        
    job_skills = job.extracted_skills or []
    
    analysis = optimization_engine.get_resume_suggestions(resume_content, job_description, job_skills)
    
    # 5. Dynamic filtering and post-processing
    # Ensure missing keywords are strictly NOT present in the resume content (case-insensitive)
    resume_content_lower = resume_content.lower()
    cleaned_missing_keywords = []
    for kw in analysis.get("missing_keywords", []):
        if kw.lower() not in resume_content_lower:
            cleaned_missing_keywords.append(kw)
    
    # Dynamically dismiss suggestions if their section has optimized content
    filtered_suggestions = []
    for sug in analysis.get("ai_suggestions", []):
        title_lower = sug.get("title", "").lower()
        if "summary" in title_lower and has_optimized_summary:
            continue
        if "skills" in title_lower and has_optimized_skills:
            continue
        if ("experience" in title_lower or "impact" in title_lower or "metrics" in title_lower) and has_optimized_experience:
            continue
        if "certifications" in title_lower and has_optimized_certifications:
            continue
        filtered_suggestions.append(
            AISuggestionItem(
                title=sug.get("title", "Improvement Suggestion"),
                description=sug.get("description", ""),
                impact=sug.get("impact", "medium")
            )
        )
        
    # If the user has resolved all missing keywords, filter out the skills improvement suggestion
    if len(cleaned_missing_keywords) == 0:
        filtered_suggestions = [s for s in filtered_suggestions if "skills" not in s.title.lower()]
        
    return ResumeSuggestionsResponse(
        missing_keywords=cleaned_missing_keywords,
        ai_suggestions=filtered_suggestions
    )


@router.post("/resumes/download-pdf")
async def download_resume_pdf(
    request: Request,
    current_user: User = Depends(require_candidate)
):
    """
    Generate and download a PDF version of the resume.
    Accepts either:
    1. A raw HTML body (Content-Type: text/html or text/plain)
    2. A JSON body with {"html_content": "<html_string>"} (Content-Type: application/json)
    """
    import json
    import re
    import logging
    
    logger = logging.getLogger(__name__)
    content_type = request.headers.get("Content-Type", "")
    body_bytes = await request.body()
    
    html_content = ""
    if "application/json" in content_type:
        try:
            # Try parsing as standard JSON
            payload = json.loads(body_bytes.decode("utf-8"))
            html_content = payload.get("html_content", "")
        except Exception as json_err:
            logger.warning("Standard JSON parsing failed, attempting lenient regex/cleaning fallback: %s", json_err)
            body_str = body_bytes.decode("utf-8").strip()
            
            # Extract content between first double quote after "html_content" and the last double quote
            key_index = body_str.find('"html_content"')
            if key_index != -1:
                colon_index = body_str.find(':', key_index)
                if colon_index != -1:
                    start_quote = body_str.find('"', colon_index)
                    if start_quote != -1:
                        end_quote = body_str.rfind('"')
                        if end_quote > start_quote:
                            html_content = body_str[start_quote + 1:end_quote]
            
            if not html_content:
                cleaned_str = body_str
                if cleaned_str.startswith("{"):
                    cleaned_str = cleaned_str[1:].strip()
                if cleaned_str.endswith("}"):
                    cleaned_str = cleaned_str[:-1].strip()
                if cleaned_str.startswith('"html_content"'):
                    cleaned_str = cleaned_str[len('"html_content"'):].strip()
                    if cleaned_str.startswith(":"):
                        cleaned_str = cleaned_str[1:].strip()
                if cleaned_str.startswith('"') and cleaned_str.endswith('"'):
                    cleaned_str = cleaned_str[1:-1]
                html_content = cleaned_str
    else:
        # Raw HTML body
        html_content = body_bytes.decode("utf-8")

    if not html_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTML content is required."
        )

    try:
        # Resolve escape sequences if they are represented as literal chars
        if "\\n" in html_content:
            html_content = html_content.replace("\\n", "\n")
        if "\\t" in html_content:
            html_content = html_content.replace("\\t", "\t")
        if '\\"' in html_content:
            html_content = html_content.replace('\\"', '"')
        if "\\'" in html_content:
            html_content = html_content.replace("\\'", "'")
            
        pdf_bytes = pdf_service.convert_html_to_pdf(html_content)
        
        import io
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="resume.pdf"',
                "Content-Length": str(len(pdf_bytes))
            }
        )
    except Exception as e:
        logger.error("Failed to generate PDF: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}"
        )


@router.post("/resumes", response_model=ResumeVersionResponse)
def upload_resume(
    data: ResumeUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Save a manually uploaded resume from S3 URL."""
    candidate = get_candidate(current_user, db)
    
    # Check if this resume was already parsed during the upload stage
    existing_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.file_url == data.file_url
    ).first()
    
    if existing_resume:
        if data.file_name and existing_resume.file_name != data.file_name:
            existing_resume.file_name = data.file_name
            db.add(existing_resume)
            db.commit()
            db.refresh(existing_resume)
        new_resume = existing_resume
    else:
        existing_resumes = db.query(Resume).filter(Resume.candidate_id == candidate.id).all()
        is_primary = len(existing_resumes) == 0
        
        from app.services.resume_parser import resume_parser_service
        new_resume = resume_parser_service.parse_and_save_resume(
            db=db,
            candidate=candidate,
            file_url=data.file_url,
            file_name=data.file_name,
            is_primary=is_primary
        )
    
    return ResumeVersionResponse(
        id=new_resume.id,
        file_name=new_resume.file_name,
        file_url=s3_service.get_presigned_url(new_resume.file_url),
        version_number=new_resume.version_number,
        is_primary=new_resume.is_primary,
        is_ai_optimized=new_resume.is_ai_optimized,
        created_at=new_resume.created_at,
        job_id=None,
        job_title=None,
        company_name=None,
        ai_score=None
    )


@router.post("/resumes/{resume_id}/set-default")
def set_default_resume(
    resume_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Set a resume version as the default/primary one."""
    candidate = get_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.candidate_id == candidate.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
        
    # Deactivate all
    db.query(Resume).filter(Resume.candidate_id == candidate.id).update({Resume.is_primary: False})
    
    # Set this one
    resume.is_primary = True
    db.commit()
    return {"message": "Resume set as default successfully."}


@router.post("/resumes/{resume_id}/reoptimize")
def reoptimize_resume(
    resume_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Reoptimize an existing optimized resume version for its target job."""
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.candidate_id == candidate.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    if not resume.job_id:
        raise HTTPException(status_code=400, detail="This resume is not linked to any job for optimization.")
        
    job = db.query(JobPosting).filter(JobPosting.id == resume.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Target job not found.")
        
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    # Enforce limit for Free Plan resume optimization limit
    if limits["monthly_resume_optimization_limit"] < 9999:
        if candidate.resume_optimizations_used_this_month >= limits["monthly_resume_optimization_limit"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"You have reached your monthly Resume Optimization limit of {limits['monthly_resume_optimization_limit']}."
            )
            
    # Deduct credit via CreditManager (Cost: 10 AI credits)
    credit_manager.check_and_deduct_credits(
        candidate=candidate,
        cost=CreditManager.COST_RESUME_OPTIMIZATION,
        limits=limits,
        db=db
    )
    
    # Optimize existing sections
    new_sections = []
    for section in resume.sections:
        result = optimization_engine.optimize_section(job, section)
        
        section.optimized_content = result.get("optimized_content")
        section.optimization_metadata = {
            "missing_keywords": result.get("missing_keywords", []),
            "feedback": result.get("optimization_feedback", "")
        }
        db.add(section)
        new_sections.append(section)
        
    # Re-union skills just in case job skills updated
    resume.extracted_skills = list(set(resume.extracted_skills or []) | set(job.extracted_skills or []))
    
    # Update structured_data using the optimized sections
    from sqlalchemy.orm.attributes import flag_modified
    resume.structured_data = update_structured_data_with_optimized_sections(resume.structured_data, new_sections)
    flag_modified(resume, "structured_data")
    
    candidate.resume_optimizations_used_this_month += 1
    db.add(candidate)
    
    db.add(resume)
    db.commit()
    db.refresh(resume)
    
    return format_resume_structure(resume, candidate, current_user)


@router.delete("/resumes/{resume_id}")
def delete_resume(
    resume_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Delete a saved resume version (cannot delete default primary)."""
    candidate = get_candidate(current_user, db)
    resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.candidate_id == candidate.id,
        Resume.is_deleted == False
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    if resume.is_primary:
        raise HTTPException(status_code=400, detail="Cannot delete default (primary) resume.")
        
    # Check if the resume is used in any job application
    has_applied = False
    if resume.job_id:
        has_applied = db.query(JobApplication).filter(
            JobApplication.candidate_id == candidate.id,
            JobApplication.job_id == resume.job_id
        ).first() is not None

    if has_applied:
        # Soft delete
        resume.is_deleted = True
        db.add(resume)
    else:
        # Hard delete
        db.delete(resume)
        
    db.commit()
    return {"message": "Resume deleted successfully."}


# --- SAVED COVER LETTERS MANAGEMENT ---

@router.get("/cover-letters", response_model=PaginatedCoverLetterDetailResponse)
def list_cover_letters(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """List all saved cover letters for the candidate."""
    candidate = get_candidate(current_user, db)
    cover_letters = db.query(CoverLetter).filter(
        CoverLetter.candidate_id == candidate.id
    ).order_by(
        CoverLetter.created_at.desc()
    ).all()
    
    response = []
    matching_service = MatchingEngine(db)
    for cl in cover_letters:
        job_title = None
        company_name = None
        ai_score = None
        if cl.job_id:
            job = db.query(JobPosting).filter(JobPosting.id == cl.job_id).first()
            if job:
                job_title = job.title
                company_name = job.company.name if job.company else None
                
                # Get default resume AI match score for context
                primary_resume = db.query(Resume).filter(
                    Resume.candidate_id == candidate.id,
                    Resume.is_primary == True
                ).first()
                if primary_resume:
                     try:
                         score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
                         ai_score = int(score_details["final_score"])
                     except Exception:
                         ai_score = None
                          
        response.append(
            CoverLetterDetailResponse(
                id=cl.id,
                job_id=cl.job_id,
                job_title=job_title,
                company_name=company_name,
                title=cl.title,
                content=s3_service.get_presigned_url(cl.content) if cl.content else "",
                is_default=cl.is_default,
                created_at=cl.created_at,
                updated_at=cl.updated_at,
                ai_score=ai_score
            )
        )
    return {"cover_letters": response[skip : skip + limit], "count": len(response)}


@router.post("/cover-letters", response_model=CoverLetterDetailResponse)
def create_cover_letter(
    data: CoverLetterCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Save a manually created or uploaded cover letter."""
    candidate = get_candidate(current_user, db)
    existing = db.query(CoverLetter).filter(CoverLetter.candidate_id == candidate.id).all()
    is_default = len(existing) == 0
    
    title = data.title or data.file_name or "Untitled Cover Letter"
    content = data.content or data.file_url
    if not content:
        raise HTTPException(
            status_code=400,
            detail="Either content or file_url must be provided."
        )
        
    new_cl = CoverLetter(
        candidate_id=candidate.id,
        job_id=data.job_id,
        title=title,
        content=content,
        is_default=is_default
    )
    db.add(new_cl)
    db.commit()
    db.refresh(new_cl)
    
    job_title = None
    company_name = None
    if new_cl.job_id:
        job = db.query(JobPosting).filter(JobPosting.id == new_cl.job_id).first()
        if job:
            job_title = job.title
            company_name = job.company.name if job.company else None
            
    return CoverLetterDetailResponse(
        id=new_cl.id,
        job_id=new_cl.job_id,
        job_title=job_title,
        company_name=company_name,
        title=new_cl.title,
        content=s3_service.get_presigned_url(new_cl.content) if new_cl.content else "",
        is_default=new_cl.is_default,
        created_at=new_cl.created_at,
        updated_at=new_cl.updated_at,
        ai_score=None
    )


@router.put("/cover-letters/{cover_letter_id}", response_model=CoverLetterDetailResponse)
def update_cover_letter(
    cover_letter_id: UUID,
    data: CoverLetterUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Update title or content of an existing cover letter."""
    candidate = get_candidate(current_user, db)
    cl = db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id, CoverLetter.candidate_id == candidate.id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found.")
        
    if data.title is not None:
        cl.title = data.title
    if data.content is not None:
        cl.content = data.content
        
    db.commit()
    db.refresh(cl)
    
    job_title = None
    company_name = None
    if cl.job_id:
        job = db.query(JobPosting).filter(JobPosting.id == cl.job_id).first()
        if job:
            job_title = job.title
            company_name = job.company.name if job.company else None
            
    return CoverLetterDetailResponse(
        id=cl.id,
        job_id=cl.job_id,
        job_title=job_title,
        company_name=company_name,
        title=cl.title,
        content=s3_service.get_presigned_url(cl.content) if cl.content else "",
        is_default=cl.is_default,
        created_at=cl.created_at,
        updated_at=cl.updated_at,
        ai_score=None
    )


@router.post("/cover-letters/{cover_letter_id}/set-default")
def set_default_cover_letter(
    cover_letter_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Set a cover letter as the default cover letter."""
    candidate = get_candidate(current_user, db)
    cl = db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id, CoverLetter.candidate_id == candidate.id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found.")
        
    # Reset all
    db.query(CoverLetter).filter(CoverLetter.candidate_id == candidate.id).update({CoverLetter.is_default: False})
    
    # Set default
    cl.is_default = True
    db.commit()
    return {"message": "Cover letter set as default successfully."}


@router.delete("/cover-letters/{cover_letter_id}")
def delete_cover_letter(
    cover_letter_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Delete a saved cover letter (cannot delete default cover letter)."""
    candidate = get_candidate(current_user, db)
    cl = db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id, CoverLetter.candidate_id == candidate.id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found.")
    if cl.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default cover letter.")
        
    db.delete(cl)
    db.commit()
    return {"message": "Cover letter deleted successfully."}


@router.post("/cover-letters/{cover_letter_id}/reoptimize", response_model=CoverLetterResponse)
def reoptimize_cover_letter(
    cover_letter_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Reoptimize cover letter by generating it again for its linked job."""
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    cl = db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id, CoverLetter.candidate_id == candidate.id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found.")
    if not cl.job_id:
        raise HTTPException(status_code=400, detail="This cover letter is not linked to any job for re-generation.")
        
    job = db.query(JobPosting).filter(JobPosting.id == cl.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Target job not found.")
        
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    # Enforce limit for Free Plan cover letter limit
    if limits["monthly_cover_letter_limit"] < 9999:
        if limits["monthly_cover_letter_limit"] == 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="The Free plan only supports manual upload of cover letters. Please upgrade to a paid plan to use AI generation."
            )
        elif candidate.cover_letters_generated_this_month >= limits["monthly_cover_letter_limit"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"You have reached your monthly Cover Letter Generation limit of {limits['monthly_cover_letter_limit']}."
            )
            
    # Deduct credit via CreditManager (Cost: 3 AI credits)
    credit_manager.check_and_deduct_credits(
        candidate=candidate,
        cost=CreditManager.COST_COVER_LETTER_GENERATION,
        limits=limits,
        db=db
    )
    
    # Get primary resume summary section
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    if not primary_resume:
        raise HTTPException(status_code=400, detail="You do not have a primary resume uploaded.")
        
    resume_skills = ", ".join(primary_resume.extracted_skills) if primary_resume.extracted_skills else "None"
    
    # Call Gemini to generate cover letter
    import google.generativeai as genai
    from app.core.config import settings
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    prompt = f"""
    You are an expert career assistant. Generate a highly professional, compelling, and customized cover letter for:
    
    --- JOB POSITION ---
    Title: {job.title}
    Company: {job.company.name if job.company else "Target Company"}
    Description: {job.description}
    
    --- CANDIDATE PROFILE ---
    Name: {candidate.full_name}
    Skills: {resume_skills}
    
    Generate a 3-4 paragraph cover letter. Tone should be professional, warm, and confident. Avoid generic platitudes. Output only the cover letter body.
    """
    
    try:
        response = model.generate_content(prompt)
        cover_letter_text = response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate cover letter with Gemini: {e}")
        
    cl.content = cover_letter_text
    db.add(cl)
    
    candidate.cover_letters_generated_this_month += 1
    db.add(candidate)
    db.commit()
    
    return CoverLetterResponse(cover_letter=cover_letter_text)


@router.delete("/cover-letters/{cover_letter_id}")
def delete_cover_letter(
    cover_letter_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """Delete a saved cover letter."""
    candidate = get_candidate(current_user, db)
    cl = db.query(CoverLetter).filter(CoverLetter.id == cover_letter_id, CoverLetter.candidate_id == candidate.id).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found.")
        
    db.delete(cl)
    db.commit()
    return {"message": "Cover letter deleted successfully."}


@router.post("/preferences", response_model=CandidatePreferencesResponse)
def update_preferences(
    payload: CandidatePreferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    
    candidate.pref_role_type = payload.role_type
    candidate.pref_locations = payload.preferred_location
    candidate.pref_min_salary = payload.min_salary
    
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    
    preferences_exist = bool(
        candidate.pref_role_type or 
        candidate.pref_locations or 
        candidate.pref_min_salary is not None
    )
    
    return CandidatePreferencesResponse(
        role_type=candidate.pref_role_type,
        preferred_location=candidate.pref_locations,
        min_salary=candidate.pref_min_salary,
        preferences_exist=preferences_exist
    )


@router.get("/preferences", response_model=CandidatePreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    
    preferences_exist = bool(
        candidate.pref_role_type or 
        candidate.pref_locations or 
        candidate.pref_min_salary is not None
    )
    
    return CandidatePreferencesResponse(
        role_type=candidate.pref_role_type,
        preferred_location=candidate.pref_locations,
        min_salary=candidate.pref_min_salary,
        preferences_exist=preferences_exist
    )


@router.post("/auto-apply/skip/{job_id}")
def skip_job_from_auto_apply(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
        
    existing_skip = db.query(CandidateSkippedJob).filter(
        CandidateSkippedJob.candidate_id == candidate.id,
        CandidateSkippedJob.job_id == job_id
    ).first()
    
    if existing_skip:
        return {"message": "Job already skipped."}
        
    new_skip = CandidateSkippedJob(
        candidate_id=candidate.id,
        job_id=job_id
    )
    db.add(new_skip)
    db.commit()
    
    return {"message": "Job skipped successfully from auto apply."}


@router.get("/auto-apply/jobs", response_model=List[JobSeekerFeedResponse])
def get_auto_apply_jobs(
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    if limits["daily_apply_limit"] == 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Auto-apply is not available on the Free plan. Please upgrade to Silver or Gold."
        )

    plan_limit = limits["daily_apply_limit"]
    remaining_monthly = (limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used) // 2
    plan_limit = min(plan_limit, remaining_monthly)
    if limit is None:
        limit = plan_limit
    else:
        limit = min(limit, plan_limit)

    if candidate.daily_apply_credits_used >= limits["daily_apply_limit"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"You have reached your daily apply limit of {limits['daily_apply_limit']} for the {limits['name']} plan."
        )
    if (limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used) < 2:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="You do not have enough monthly AI credits to auto-apply (each application costs 2 credits)."
        )
        
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    
    if not primary_resume:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload and set a primary resume before using auto-apply."
        )
        
    # Query all active job postings
    query = (
        db.query(JobPosting)
        .options(
            joinedload(JobPosting.company),
            joinedload(JobPosting.city),
            joinedload(JobPosting.state),
            joinedload(JobPosting.country),
            joinedload(JobPosting.work_mode),
            joinedload(JobPosting.employment_type),
            joinedload(JobPosting.currency),
        )
        .filter(JobPosting.is_active == True)
    )
    
    # Exclude already applied jobs
    applied_job_ids = db.query(JobApplication.job_id).filter(
        JobApplication.candidate_id == candidate.id
    ).all()
    applied_ids = [r[0] for r in applied_job_ids]
    if applied_ids:
        query = query.filter(JobPosting.id.not_in(applied_ids))
        
    # Exclude skipped jobs
    skipped_job_ids = db.query(CandidateSkippedJob.job_id).filter(
        CandidateSkippedJob.candidate_id == candidate.id
    ).all()
    skipped_ids = [r[0] for r in skipped_job_ids]
    if skipped_ids:
        query = query.filter(JobPosting.id.not_in(skipped_ids))
        
    jobs = query.all()
    
    # Filter and score
    matching_service = MatchingEngine(db)
    scored_jobs = []
    
    pref_roles = [r.strip().lower() for r in candidate.pref_role_type.split(",") if r.strip()] if candidate.pref_role_type else []
    pref_locs = [l.strip().lower() for l in candidate.pref_locations.split(",") if l.strip()] if candidate.pref_locations else []
    
    for job in jobs:
        # Check role type match
        if pref_roles:
            job_title = job.title.lower() if job.title else ""
            if not any(role in job_title for role in pref_roles):
                continue
                
        # Check location match
        if pref_locs:
            match_loc = False
            if "remote" in pref_locs and job.work_mode and job.work_mode.name.lower() == "remote":
                match_loc = True
            else:
                city_name = job.city.name.lower() if job.city and job.city.name else ""
                state_name = job.state.name.lower() if job.state and job.state.name else ""
                country_name = job.country.name.lower() if job.country and job.country.name else ""
                if any(loc in city_name or loc in state_name or loc in country_name for loc in pref_locs if loc != "remote"):
                    match_loc = True
            if not match_loc:
                continue
                
        # Check salary match
        if candidate.pref_min_salary is not None:
            if job.salary_max is not None and job.salary_max < candidate.pref_min_salary:
                continue
            if job.salary_max is None and job.salary_min is not None and job.salary_min < candidate.pref_min_salary:
                continue
                
        # Calculate AI score
        ai_score = 0
        if primary_resume.overall_embedding is not None:
            try:
                score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
                
        scored_jobs.append((job, ai_score))
        
    scored_jobs.sort(key=lambda x: x[1], reverse=True)
    top_jobs = scored_jobs[:limit]
    
    feed_items = []
    for job, ai_score in top_jobs:
        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None
        
        # Check if saved
        is_saved = db.query(SavedJob).filter(SavedJob.candidate_id == candidate.id, SavedJob.job_id == job.id).first() is not None
        
        feed_items.append(
            JobSeekerFeedResponse(
                id=job.id,
                company_id=job.company_id,
                company_name=job.company.name if job.company else None,
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
                company_verified=True,
                job_title=job.title,
                ai_score=ai_score,
                city=city_name,
                state=state_name,
                country=country_name,
                location_label=_build_location_label(city_name, state_name, country_name),
                work_mode=job.work_mode.name if job.work_mode else None,
                sponsorship_label=_build_sponsorship_label(job),
                posted_at=job.created_at,
                posted_ago=_format_posted_ago(job.created_at),
                experience_min_years=job.min_experience_years,
                experience_max_years=job.max_experience_years,
                experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
                salary_min=job.salary_min * 12 if job.salary_min is not None else None,
                salary_max=job.salary_max * 12 if job.salary_max is not None else None,
                salary_currency_code=currency_code,
                salary_currency_symbol=currency_symbol,
                salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code),
                employment_type=job.employment_type.name if job.employment_type else None,
                save_action="unsave" if is_saved else "save",
                apply_action="apply",
                saved=is_saved,
                applied=False,
                application_status=None,
                coverLetter=job.cover_letter_required
            )
        )
        
    return feed_items


@router.post("/auto-apply/execute", response_model=List[JobApplicationResponse])
def execute_auto_apply(
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Executes the auto-apply functionality. Automatically applies to the top matched jobs
    using the candidate's primary resume, provided the candidate has sufficient credits.
    Sets application status to 'auto-apply'.
    """
    candidate = get_candidate(current_user, db)
    candidate = check_and_reset_candidate_credits(candidate, db)
    
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    if limits["daily_apply_limit"] == 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Auto-apply is not available on the Free plan. Please upgrade to Silver or Gold."
        )

    plan_limit = limits["daily_apply_limit"]
    remaining_monthly = (limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used) // 2
    plan_limit = min(plan_limit, remaining_monthly)
    if limit is None:
        limit = plan_limit
    else:
        limit = min(limit, plan_limit)
    
    # 1. Check if candidate has any daily / monthly credits remaining
    if candidate.daily_apply_credits_used >= limits["daily_apply_limit"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"You have reached your daily apply limit of {limits['daily_apply_limit']} for the {limits['name']} plan."
        )
    if (limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used) < 2:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="You do not have enough monthly AI credits to auto-apply (each application costs 2 credits)."
        )
        
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    
    if not primary_resume:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload and set a primary resume before using auto-apply."
        )
        
    # Get auto apply eligible jobs (ordered by AI score)
    query = (
        db.query(JobPosting)
        .options(joinedload(JobPosting.company))
        .filter(JobPosting.is_active == True)
    )
    
    # Exclude already applied
    applied_job_ids = db.query(JobApplication.job_id).filter(
        JobApplication.candidate_id == candidate.id
    ).all()
    applied_ids = [r[0] for r in applied_job_ids]
    if applied_ids:
        query = query.filter(JobPosting.id.not_in(applied_ids))
        
    # Exclude skipped
    skipped_job_ids = db.query(CandidateSkippedJob.job_id).filter(
        CandidateSkippedJob.candidate_id == candidate.id
    ).all()
    skipped_ids = [r[0] for r in skipped_job_ids]
    if skipped_ids:
        query = query.filter(JobPosting.id.not_in(skipped_ids))
        
    jobs = query.all()
    
    matching_service = MatchingEngine(db)
    scored_jobs = []
    
    pref_roles = [r.strip().lower() for r in candidate.pref_role_type.split(",") if r.strip()] if candidate.pref_role_type else []
    pref_locs = [l.strip().lower() for l in candidate.pref_locations.split(",") if l.strip()] if candidate.pref_locations else []
    
    for job in jobs:
        # Check role type match
        if pref_roles:
            job_title = job.title.lower() if job.title else ""
            if not any(role in job_title for role in pref_roles):
                continue
                
        # Check location match
        if pref_locs:
            match_loc = False
            if "remote" in pref_locs and job.work_mode and job.work_mode.name.lower() == "remote":
                match_loc = True
            else:
                city_name = job.city.name.lower() if job.city and job.city.name else ""
                state_name = job.state.name.lower() if job.state and job.state.name else ""
                country_name = job.country.name.lower() if job.country and job.country.name else ""
                if any(loc in city_name or loc in state_name or loc in country_name for loc in pref_locs if loc != "remote"):
                    match_loc = True
            if not match_loc:
                continue
                
        # Check salary match
        if candidate.pref_min_salary is not None:
            if job.salary_max is not None and job.salary_max < candidate.pref_min_salary:
                continue
            if job.salary_max is None and job.salary_min is not None and job.salary_min < candidate.pref_min_salary:
                continue
                
        # Calculate AI score
        ai_score = 0
        if primary_resume.overall_embedding is not None:
            try:
                score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
                
        scored_jobs.append((job, ai_score))
        
    scored_jobs.sort(key=lambda x: x[1], reverse=True)
    
    remaining_daily = limits["daily_apply_limit"] - candidate.daily_apply_credits_used
    remaining_monthly = (limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used) // 2
    max_to_apply = min(limit, remaining_daily, remaining_monthly)
    
    top_matches = scored_jobs[:max_to_apply]
    
    applied_responses = []
    for job, ai_score in top_matches:
        # Determine status: "shortlisted" if ai_score matches or exceeds job's threshold (or default 70)
        threshold = job.ai_score_threshold if (job.ai_score_threshold and job.ai_score_threshold > 0) else 70
        app_status = "shortlisted" if ai_score >= threshold else "applied"

        new_app = JobApplication(
            candidate_id=candidate.id,
            job_id=job.id,
            status=app_status,
            apply_mode="auto-apply"
        )
        
        # Deduct credit
        candidate.daily_apply_credits_used += 1
        candidate.monthly_ai_credits_used += 2
        
        db.add(new_app)
        db.commit()
        db.refresh(new_app)
        
        # Format location label
        work_mode_str = job.work_mode.name.title() if job.work_mode else None
        location_parts = []
        if job.city:
            location_parts.append(job.city.name)
        if job.state:
            state_part = job.state.code or job.state.name
            location_parts.append(state_part)
            
        base_loc = ", ".join(location_parts) if location_parts else None
        if base_loc and work_mode_str:
            location_label = f"{base_loc} ({work_mode_str})"
        elif work_mode_str:
            location_label = work_mode_str
        elif base_loc:
            location_label = base_loc
        else:
            location_label = "Remote"

        applied_responses.append(
            JobApplicationResponse(
                id=new_app.id,
                job_id=job.id,
                job_title=job.title,
                company_name=job.company.name if job.company else None,
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
                status=new_app.status,
                apply_mode=new_app.apply_mode,
                applied_at=new_app.created_at,
                match_score=ai_score,
                location_label=location_label,
                status_label="Shortlisted" if new_app.status == "shortlisted" else "Applied"
            )
        )
        
    if applied_responses:
        db.add(candidate)
        db.commit()
        
    return applied_responses


@router.get("/auto-apply/history", response_model=List[JobSeekerFeedResponse])
def get_auto_apply_history(
    search: Optional[str] = None,
    work_type: Optional[str] = None,
    job_type: Optional[str] = None,
    location: Optional[str] = None,
    match_score: Optional[str] = None,
    job_post_date: Optional[str] = None,
    visa_sponsorship: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Get all job applications for the candidate with full support for filters (similar to job-seeker dashboard).
    """
    candidate = get_candidate(current_user, db)
    
    # Start with JobApplication query
    query = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(JobApplication.candidate_id == candidate.id, JobPosting.is_active == True, JobApplication.apply_mode == "auto-apply")
    )
    
    # Apply search filter
    if search:
        query = query.join(Company, JobPosting.company_id == Company.id).filter(
            or_(
                JobPosting.title.ilike(f"%{search}%"),
                Company.name.ilike(f"%{search}%")
            )
        )
        
    # Apply work type filter
    if work_type and work_type.lower() != "all":
        query = query.filter(JobPosting.work_mode.has(name=work_type.upper()))
        
    # Apply job type filter
    if job_type and job_type.lower() != "all":
        norm_jt = job_type.replace("-", "_").upper()
        query = query.filter(JobPosting.employment_type.has(name=norm_jt))
        
    # Apply location country filter
    if location and location.lower() != "all":
        if location.lower() in ("u.s.", "us", "united states"):
            query = query.join(JobPosting.country).filter(JobPosting.country.has(iso_code="US"))
        elif location.lower() in ("india", "in"):
            query = query.join(JobPosting.country).filter(JobPosting.country.has(iso_code="IN"))
            
    # Apply visa sponsorship filter
    if visa_sponsorship and visa_sponsorship.lower() != "all":
        if visa_sponsorship.lower() == "h1b sponsorship":
            query = query.filter(JobPosting.visa_status.has(name="H-1B Visa"))
        elif visa_sponsorship.lower() == "sponsorship available":
            query = query.filter(or_(JobPosting.requires_visa_sponsorship.isnot(None), JobPosting.must_be_authorized_to_work == False))
        elif visa_sponsorship.lower() == "no sponsorship":
            query = query.filter(JobPosting.requires_visa_sponsorship.is_(None))
            
    # Apply salary filters
    if salary_min is not None:
        query = query.filter(JobPosting.salary_min >= salary_min)
    if salary_max is not None:
        query = query.filter(JobPosting.salary_max <= salary_max)
        
    # Apply job post date filter
    if job_post_date:
        now = datetime.now(timezone.utc)
        if job_post_date.lower() == "today" or job_post_date.lower() == "within 24 hour":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=1))
        elif job_post_date.lower() == "last 7 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=7))
        elif job_post_date.lower() == "last 30 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=30))
            
    query = query.order_by(JobApplication.created_at.desc())
    
    # If match_score filter is not active, we can paginate in the database
    if not match_score or match_score.lower() == "all":
        query = query.offset(skip).limit(limit)
        
    applications = query.all()
    
    primary_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.is_primary == True
    ).first()
    
    matching_service = MatchingEngine(db)
    history_items = []
    
    for app in applications:
        job = app.job
        
        # Calculate AI match score
        ai_score = 0
        if primary_resume and primary_resume.overall_embedding is not None:
            try:
                score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
                
        # Filter by Match Score in Python if specified
        if match_score and match_score.lower() != "all":
            if match_score == "90%+" and ai_score < 90:
                continue
            elif match_score == "80 – 89%" and not (80 <= ai_score <= 89):
                continue
            elif match_score == "70 – 79%" and not (70 <= ai_score <= 79):
                continue
            elif match_score == "Below 70%" and ai_score >= 70:
                continue
                
        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None
        
        # Check if saved
        is_saved = db.query(SavedJob).filter(SavedJob.candidate_id == candidate.id, SavedJob.job_id == job.id).first() is not None
        
        history_items.append(
            JobSeekerFeedResponse(
                id=job.id,
                company_id=job.company_id,
                company_name=job.company.name if job.company else None,
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
                company_verified=True,
                job_title=job.title,
                ai_score=ai_score,
                city=city_name,
                state=state_name,
                country=country_name,
                location_label=_build_location_label(city_name, state_name, country_name),
                work_mode=job.work_mode.name if job.work_mode else None,
                sponsorship_label=_build_sponsorship_label(job),
                posted_at=job.created_at,
                posted_ago=_format_posted_ago(job.created_at),
                experience_min_years=job.min_experience_years,
                experience_max_years=job.max_experience_years,
                experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
                salary_min=job.salary_min * 12 if job.salary_min is not None else None,
                salary_max=job.salary_max * 12 if job.salary_max is not None else None,
                salary_currency_code=currency_code,
                salary_currency_symbol=currency_symbol,
                salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code),
                employment_type=job.employment_type.name if job.employment_type else None,
                save_action="unsave" if is_saved else "save",
                apply_action="applied",
                saved=is_saved,
                applied=True,
                application_status=app.status,
                apply_mode=app.apply_mode,
                coverLetter=job.cover_letter_required
            )
        )
        
    if not match_score or match_score.lower() == "all":
        return history_items
    return history_items[skip : skip + limit]

@router.get("/profile", response_model=CandidateProfileResponse)
def get_candidate_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Get the profile details of the authenticated candidate.
    """
    candidate = get_candidate(current_user, db)
    return CandidateProfileResponse(
        id=candidate.id,
        user_id=candidate.user_id,
        email=current_user.email,
        full_name=candidate.full_name,
        phone=candidate.phone,
        profile_picture=s3_service.get_presigned_url(candidate.profile_picture),
        onboarding_step=candidate.onboarding_step,
        onboarding_completed=candidate.onboarding_completed,
        work_status_id=candidate.work_status_id,
        taxonomy_domain_id=candidate.taxonomy_domain_id,
        visa_status_id=candidate.visa_status_id,
        current_address=candidate.current_address,
        experience_level=candidate.experience_level,
        experience_years=candidate.experience_years,
        linkedin_url=candidate.linkedin_url,
        portfolio_url=candidate.portfolio_url,
        about_summary=candidate.about_summary,
        is_phone_verified=candidate.is_phone_verified,
        pref_role_type=candidate.pref_role_type,
        pref_locations=candidate.pref_locations,
        pref_min_salary=candidate.pref_min_salary
    )

@router.put("/profile", response_model=CandidateProfileResponse)
def update_candidate_profile(
    profile_data: CandidateProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Update the profile details of the authenticated candidate.
    """
    candidate = get_candidate(current_user, db)
    
    # Validation checks for ForeignKey references (Must exist in database)
    if profile_data.visa_status_id is not None:
        visa = db.query(MetaVisaStatus).filter(MetaVisaStatus.id == profile_data.visa_status_id).first()
        if not visa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid visa_status_id: record does not exist")
            
    if profile_data.work_status_id is not None:
        work = db.query(MetaWorkStatus).filter(MetaWorkStatus.id == profile_data.work_status_id).first()
        if not work:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid work_status_id: record does not exist")

    if profile_data.taxonomy_domain_id is not None:
        domain = db.query(TaxonomyDomain).filter(TaxonomyDomain.id == profile_data.taxonomy_domain_id).first()
        if not domain:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid taxonomy_domain_id: record does not exist")

    # Update candidate fields
    for field, value in profile_data.model_dump(exclude_unset=True).items():
        setattr(candidate, field, value)
        
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    
    return CandidateProfileResponse(
        id=candidate.id,
        user_id=candidate.user_id,
        email=current_user.email,
        full_name=candidate.full_name,
        phone=candidate.phone,
        profile_picture=s3_service.get_presigned_url(candidate.profile_picture),
        onboarding_step=candidate.onboarding_step,
        onboarding_completed=candidate.onboarding_completed,
        work_status_id=candidate.work_status_id,
        taxonomy_domain_id=candidate.taxonomy_domain_id,
        visa_status_id=candidate.visa_status_id,
        current_address=candidate.current_address,
        experience_level=candidate.experience_level,
        experience_years=candidate.experience_years,
        linkedin_url=candidate.linkedin_url,
        portfolio_url=candidate.portfolio_url,
        about_summary=candidate.about_summary,
        is_phone_verified=candidate.is_phone_verified,
        pref_role_type=candidate.pref_role_type,
        pref_locations=candidate.pref_locations,
        pref_min_salary=candidate.pref_min_salary
    )

@router.delete("/profile/picture", response_model=CandidateProfileResponse)
def delete_candidate_profile_picture(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Delete the profile picture of the authenticated candidate.
    """
    candidate = get_candidate(current_user, db)
    candidate.profile_picture = None
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    
    return CandidateProfileResponse(
        id=candidate.id,
        user_id=candidate.user_id,
        email=current_user.email,
        full_name=candidate.full_name,
        phone=candidate.phone,
        profile_picture=None,
        onboarding_step=candidate.onboarding_step,
        onboarding_completed=candidate.onboarding_completed,
        work_status_id=candidate.work_status_id,
        taxonomy_domain_id=candidate.taxonomy_domain_id,
        visa_status_id=candidate.visa_status_id,
        current_address=candidate.current_address,
        experience_level=candidate.experience_level,
        experience_years=candidate.experience_years,
        linkedin_url=candidate.linkedin_url,
        portfolio_url=candidate.portfolio_url,
        about_summary=candidate.about_summary,
        is_phone_verified=candidate.is_phone_verified,
        pref_role_type=candidate.pref_role_type,
        pref_locations=candidate.pref_locations,
        pref_min_salary=candidate.pref_min_salary
    )

@router.post("/profile/phone/send-otp", response_model=SendOTPResponse)
async def send_phone_otp(
    payload: SendOTPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Generate and mock send an OTP to the candidate's phone number.
    """
    # Rate limit check: resend allowed after approx 60 seconds
    if not OTPService.can_request_otp_by_phone(db, payload.phone, "PHONE_VERIFICATION"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting a new OTP."
        )

    # Request/Generate and store OTP (valid for 5 mins)
    success = await OTPService.request_otp_by_phone(db, payload.phone, "PHONE_VERIFICATION")
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please try again."
        )

    return SendOTPResponse(message="OTP sent successfully")

@router.post("/profile/phone/verify-otp", response_model=VerifyOTPResponse)
async def verify_phone_otp(
    payload: VerifyOTPRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Verify the phone OTP. If valid, set is_phone_verified = True on the candidate profile.
    """
    candidate = get_candidate(current_user, db)

    # Verify the code
    is_valid = await OTPService.verify_otp_by_phone(db, payload.phone, payload.otp_code, "PHONE_VERIFICATION")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP."
        )

    # If the user successfully verified a phone number that is different from candidate's current phone,
    # update the candidate's phone number.
    if candidate.phone != payload.phone:
        candidate.phone = payload.phone
    
    candidate.is_phone_verified = True

    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    return VerifyOTPResponse(
        message="Phone verified successfully",
        is_phone_verified=True
    )


@router.get("/recommended-jobs", response_model=List[JobSeekerFeedResponse])
def get_recommended_jobs(
    resume_id: Optional[UUID] = None,
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    """
    Get recommended jobs for the logged-in candidate.
    Recommendations are generated by:
    1. Querying active/published jobs (excluding those in skipped_jobs list).
    2. Ranking at database level using SQL case expressions for matching taxonomy domain and experience years.
    3. Detailed scoring of the top 100 candidate jobs using MatchingEngine (semantic embedding similarity, skills overlap, logistics, and experience).
    4. Sorting by the detailed match score descending and returning the top `limit`.
    """
    candidate = get_candidate(current_user, db)
    
    # 1. Resolve resume to use for scoring
    if resume_id:
        resume = db.query(Resume).filter(
            Resume.id == resume_id,
            Resume.candidate_id == candidate.id
        ).first()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Specified resume not found."
            )
    else:
        resume = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.is_primary == True
        ).first()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You do not have a primary resume uploaded. A resume is required to generate recommendations."
            )

    # 2. Extract experience and domain criteria
    candidate_exp = candidate.experience_years if candidate.experience_years is not None else resume.total_experience_years
    candidate_domain = candidate.taxonomy_domain_id if candidate.taxonomy_domain_id is not None else resume.taxonomy_domain_id

    # 3. Formulate exclusions subquery (exclude skipped jobs, but include applied jobs per comments)
    skipped_job_ids_query = select(CandidateSkippedJob.job_id).where(
        CandidateSkippedJob.candidate_id == candidate.id
    )

    # 4. Fetch candidate pool of jobs
    query = db.query(JobPosting).filter(
        JobPosting.is_active == True,
        JobPosting.status == JobStatus.PUBLISHED,
        ~JobPosting.id.in_(skipped_job_ids_query)
    )

    # DB-level ranking clauses
    order_by_clauses = []
    if candidate_domain:
        order_by_clauses.append(
            case(
                (JobPosting.taxonomy_domain_id == candidate_domain, 1),
                else_=0
            ).desc()
        )
    if candidate_exp is not None:
        order_by_clauses.append(
            case(
                (JobPosting.min_experience_years <= candidate_exp, 1),
                else_=0
            ).desc()
        )
    order_by_clauses.append(JobPosting.created_at.desc())

    # Get a candidate pool of up to 100 jobs for advanced matching
    jobs_pool = query.order_by(*order_by_clauses).limit(100).all()

    # 5. Score candidate jobs pool using MatchingEngine
    matching_service = MatchingEngine(db)
    scored_jobs = []
    for job in jobs_pool:
        try:
            score_details = matching_service.score_resume_object_for_job_object(resume, job)
            final_score = score_details["final_score"]
        except Exception:
            final_score = 0.0
        
        scored_jobs.append((job, final_score))

    # 6. Sort scored jobs by final score descending
    scored_jobs.sort(key=lambda x: x[1], reverse=True)

    # 7. Construct response for top recommended jobs
    feed_items = []
    for job, ai_score in scored_jobs[:limit]:
        is_saved = db.query(SavedJob).filter(
            SavedJob.candidate_id == candidate.id,
            SavedJob.job_id == job.id
        ).first() is not None
        
        app_record = db.query(JobApplication).filter(
            JobApplication.candidate_id == candidate.id,
            JobApplication.job_id == job.id
        ).first()
        is_applied = app_record is not None
        app_status = app_record.status if app_record else None
        
        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None

        feed_items.append(
            JobSeekerFeedResponse(
                id=job.id,
                company_id=job.company_id,
                company_name=job.company.name if job.company else None,
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
                company_verified=True,
                job_title=job.title,
                ai_score=int(ai_score),
                city=city_name,
                state=state_name,
                country=country_name,
                location_label=_build_location_label(city_name, state_name, country_name),
                work_mode=job.work_mode.name if job.work_mode else None,
                sponsorship_label=_build_sponsorship_label(job),
                posted_at=job.created_at,
                posted_ago=_format_posted_ago(job.created_at),
                experience_min_years=job.min_experience_years,
                experience_max_years=job.max_experience_years,
                experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency_code=currency_code,
                salary_currency_symbol=currency_symbol,
                salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code),
                employment_type=job.employment_type.name if job.employment_type else None,
                save_action="unsave" if is_saved else "save",
                apply_action="applied" if is_applied else "apply",
                saved=is_saved,
                applied=is_applied,
                application_status=app_status,
                apply_mode=app_record.apply_mode if app_record else None,
                coverLetter=job.cover_letter_required
            )
        )

    return feed_items




