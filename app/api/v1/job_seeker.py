from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, select, func

from app.db.session import get_db
from app.core.dependencies import require_candidate, get_current_active_user
from app.models.user import User, UserRole
from app.models.candidate import Candidate
from app.models.job import JobPosting
from app.models.application import JobApplication
from app.models.saved_job import SavedJob
from app.models.resume import Resume, ResumeSection
from app.services.matching_engine import MatchingEngine
from app.services.optimization_engine import optimization_engine
from app.schemas.job_seeker import (
    CandidateCreditsResponse,
    JobSeekerFeedResponse,
    JobSeekerDetailResponse,
    AIMatchOverview,
    SavedJobResponse,
    JobApplicationResponse,
    OptimizeResumeResponse,
    OptimizeSectionResult,
    CoverLetterResponse,
    FitAnalysisResponse
)
from app.api.v1.jobs import (
    _build_location_label,
    _format_experience_label,
    _format_posted_ago,
    _format_salary_range
)

router = APIRouter(prefix="/job-seeker", tags=["job-seeker"])

# Plan Limits configuration
PLAN_LIMITS = {
    "free": {
        "name": "Free",
        "daily_apply_limit": 0,
        "monthly_ai_credits": 60,
        "monthly_resume_optimization_limit": 3,
        "monthly_cover_letter_limit": 3,
        "missing_skills_analysis_enabled": False,
        "saved_resumes_limit": 7,
    },
    "pro": {
        "name": "Pro",
        "daily_apply_limit": 3,
        "monthly_ai_credits": 400,
        "monthly_resume_optimization_limit": 99999,
        "monthly_cover_letter_limit": 99999,
        "missing_skills_analysis_enabled": True,
        "saved_resumes_limit": 30,
    },
    "premium": {
        "name": "Premium",
        "daily_apply_limit": 7,
        "monthly_ai_credits": 700,
        "monthly_resume_optimization_limit": 99999,
        "monthly_cover_letter_limit": 99999,
        "missing_skills_analysis_enabled": True,
        "saved_resumes_limit": 99999,
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
    query = db.query(JobPosting).filter(JobPosting.is_active == True)
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                JobPosting.title.ilike(f"%{search}%"),
                JobPosting.description.ilike(f"%{search}%")
            )
        )
        
    # Apply work type filter
    if work_type and work_type.lower() != "all":
        query = query.join(JobPosting.work_mode).filter(func.lower(JobPosting.work_mode.has(name=work_type.upper())))
        
    # Apply job type filter
    if job_type and job_type.lower() != "all":
        norm_jt = job_type.replace("-", "_").upper()
        query = query.join(JobPosting.employment_type).filter(func.lower(JobPosting.employment_type.has(name=norm_jt)))
        
    # Apply location country filter
    if location and location.lower() != "all":
        if location.lower() in ("u.s.", "us", "united states"):
            query = query.join(JobPosting.country).filter(JobPosting.country.has(iso_code="US"))
        elif location.lower() in ("india", "in"):
            query = query.join(JobPosting.country).filter(JobPosting.country.has(iso_code="IN"))
            
    # Apply visa sponsorship filter
    if visa_sponsorship and visa_sponsorship.lower() != "all":
        if visa_sponsorship.lower() == "h1b sponsorship":
            query = query.filter(JobPosting.requires_visa_sponsorship == True)
        elif visa_sponsorship.lower() == "sponsorship available":
            query = query.filter(or_(JobPosting.requires_visa_sponsorship == True, JobPosting.must_be_authorized_to_work == False))
        elif visa_sponsorship.lower() == "no sponsorship":
            query = query.filter(JobPosting.requires_visa_sponsorship == False)
            
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
                company_logo_url=job.company.logo_url if job.company else None,
                company_verified=True,
                job_title=job.title,
                ai_score=ai_score,
                city=city_name,
                state=state_name,
                country=country_name,
                location_label=_build_location_label(city_name, state_name, country_name),
                work_mode=job.work_mode.name if job.work_mode else None,
                sponsorship_label="H1B sponsorship" if job.requires_visa_sponsorship else None,
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
                application_status=app_status
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
        company_logo_url=job.company.logo_url if job.company else None,
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
        sponsorship_label="H1B sponsorship" if job.requires_visa_sponsorship else None,
        posted_ago=_format_posted_ago(job.created_at),
        experience_label=_format_experience_label(job.min_experience_years, job.max_experience_years),
        salary_range_label=_format_salary_range(job.salary_min, job.salary_max, currency_symbol, currency_code),
        employment_type=job.employment_type.name if job.employment_type else None,
        saved=is_saved,
        applied=is_applied,
        application_status=app_status,
        ai_match_overview=match_overview
    )

@router.post("/jobs/{job_id}/apply", response_model=JobApplicationResponse)
def apply_to_job(
    job_id: UUID,
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
        
    # Enforce plan limits
    tier = candidate.plan_tier or "free"
    limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
    
    # 1. Auto apply credit check
    if candidate.daily_apply_credits_used >= limits["daily_apply_limit"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"You have reached your daily apply limit of {limits['daily_apply_limit']} for the {limits['name']} plan."
        )
        
    # 2. Monthly AI credit check
    if candidate.monthly_ai_credits_used >= limits["monthly_ai_credits"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"You have reached your monthly AI credit limit of {limits['monthly_ai_credits']}."
        )
        
    # Create application record
    new_app = JobApplication(
        candidate_id=candidate.id,
        job_id=job.id,
        status="applied"
    )
    
    # Deduct credits
    candidate.daily_apply_credits_used += 1
    candidate.monthly_ai_credits_used += 1
    
    db.add(new_app)
    db.add(candidate)
    db.commit()
    db.refresh(new_app)
    
    return JobApplicationResponse(
        id=new_app.id,
        job_id=job.id,
        job_title=job.title,
        company_name=job.company.name if job.company else None,
        company_logo_url=job.company.logo_url if job.company else None,
        status=new_app.status,
        applied_at=new_app.created_at
    )

@router.post("/jobs/{job_id}/save")
def save_or_unsave_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    job = db.query(JobPosting).filter(JobPosting.id == job_id, JobPosting.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found.")
        
    existing_save = db.query(SavedJob).filter(SavedJob.candidate_id == candidate.id, SavedJob.job_id == job.id).first()
    
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

@router.get("/applications", response_model=List[JobApplicationResponse])
def get_submitted_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    candidate = get_candidate(current_user, db)
    apps = db.query(JobApplication).filter(JobApplication.candidate_id == candidate.id).order_by(JobApplication.created_at.desc()).all()
    
    response = []
    for record in apps:
        response.append(
            JobApplicationResponse(
                id=record.id,
                job_id=record.job_id,
                job_title=record.job.title if record.job else "Unknown Position",
                company_name=record.job.company.name if record.job and record.job.company else None,
                company_logo_url=record.job.company.logo_url if record.job and record.job.company else None,
                status=record.status,
                applied_at=record.created_at
            )
        )
    return response

@router.post("/jobs/{job_id}/optimize-resume", response_model=OptimizeResumeResponse)
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
    
    # Enforce limit for Free Plan
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
        
    # Optimize resume sections
    optimized_sections = []
    for section in primary_resume.sections:
        result = optimization_engine.optimize_section(job, section)
        
        # Save optimized content
        section.optimized_content = result.get("optimized_content")
        section.optimization_metadata = {
            "missing_keywords": result.get("missing_keywords", []),
            "feedback": result.get("optimization_feedback", "")
        }
        db.add(section)
        
        optimized_sections.append(
            OptimizeSectionResult(
                section_type=section.section_type,
                original_content=section.original_content,
                optimized_content=result.get("optimized_content"),
                optimization_feedback=result.get("optimization_feedback")
            )
        )
        
    # Increment usage
    candidate.resume_optimizations_used_this_month += 1
    db.add(candidate)
    db.commit()
    
    return OptimizeResumeResponse(optimized_sections=optimized_sections)

@router.post("/jobs/{job_id}/generate-cover-letter", response_model=CoverLetterResponse)
def generate_cover_letter_for_job(
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
    
    # Enforce limit for Free Plan
    if limits["monthly_cover_letter_limit"] < 9999:
        if candidate.cover_letters_generated_this_month >= limits["monthly_cover_letter_limit"]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"You have reached your monthly Cover Letter Generation limit of {limits['monthly_cover_letter_limit']}."
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
    model = genai.GenerativeModel('gemini-2.5-flash')
    
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
        
    # Increment usage
    candidate.cover_letters_generated_this_month += 1
    db.add(candidate)
    db.commit()
    
    return CoverLetterResponse(cover_letter=cover_letter_text)

@router.post("/jobs/{job_id}/analyze-fit", response_model=FitAnalysisResponse)
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
