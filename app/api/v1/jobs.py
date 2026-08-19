from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.job import JobPosting, JobStatus
from app.models.company import Company
from app.models.user import User, UserRole
from app.models.candidate import Candidate
from app.models.saved_job import SavedJob
from app.models.application import JobApplication
from app.models.resume import Resume
from app.schemas.job import (
    JobDashboardCardResponse, JobCreate, JobResponse, JobCreateBasic, 
    JobAboutUpdate, JobWorkAuthorizationUpdate, JobCoverLetterUpdate, 
    JobPublishUpdate, JobPosterDashboardResponse, JobPosterDashboardKPIs,
    MonthlySuccessRatePoint, HiresByDomainPoint, ActionFeedItem, 
    FunnelStagePoint, JobStatusBreakdown, EmployerJobListingItem,
    PipelineStageSummary, EmployerCompanyDetails, EmployerJobDetailResponse,
    JobPosterApplicantListItem, TimelineEvent, JobPosterApplicantProfileResponse,
    JobApplicationStatusUpdateRequest, JobApplicationStatusUpdateResponse,
    JobPosterJobsStatsResponse, JobSaveDraft, BulkStatusUpdateRequest, BulkStatusUpdateResponse,
    JobCandidateStatsResponse
)
from app.services.s3_service import S3Service
from app.services.matching_engine import MatchingEngine
from app.schemas.job_seeker import JobApplicationResponse, SaveJobRequest
from app.core.dependencies import require_employer, get_optional_current_active_user, require_candidate


router = APIRouter(prefix="/job-posters", tags=["job-posters"])
job_flow_router = APIRouter(tags=["job-posters"])
s3_service = S3Service()

# Plan Limits configuration loaded dynamically from plans_service
from app.services.plans_service import POSTER_PLAN_LIMITS
from app.schemas.meta import MetaSubscriptionPlanResponse
from app.models.meta import MetaSubscriptionPlan

@router.get("/plans", response_model=List[MetaSubscriptionPlanResponse])
def get_employer_plans(db: Session = Depends(get_db)):
    """Retrieve all plans configured for Job Posters (employers), including inactive ones."""
    return db.query(MetaSubscriptionPlan).filter(
        MetaSubscriptionPlan.role == "employer"
    ).order_by(MetaSubscriptionPlan.id).all()


def _format_posted_ago(created_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    created_at_utc = created_at.astimezone(timezone.utc) if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    delta = now - created_at_utc

    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "Posted just now"

    total_minutes = total_seconds // 60
    if total_minutes < 60:
        unit = "minute" if total_minutes == 1 else "minutes"
        return f"Posted {total_minutes} {unit} ago"

    total_hours = total_minutes // 60
    if total_hours < 24:
        unit = "hour" if total_hours == 1 else "hours"
        return f"Posted {total_hours} {unit} ago"

    total_days = total_hours // 24
    unit = "day" if total_days == 1 else "days"
    return f"Posted {total_days} {unit} ago"


def _format_experience_label(min_years: Optional[int], max_years: Optional[int]) -> Optional[str]:
    if min_years is None and max_years is None:
        return None
    if min_years is not None and max_years is not None:
        return f"{min_years} - {max_years} years"
    if min_years is not None:
        suffix = "year" if min_years == 1 else "years"
        return f"{min_years}+ {suffix}"
    suffix = "year" if max_years == 1 else "years"
    return f"Up to {max_years} {suffix}"


def _format_salary_range(
    salary_min: Optional[int],
    salary_max: Optional[int],
    currency_symbol: Optional[str],
    currency_code: Optional[str],
) -> Optional[str]:
    if salary_min is None and salary_max is None:
        return None

    currency_prefix = currency_symbol or currency_code or ""
    if currency_prefix:
        currency_prefix = f"{currency_prefix}"

    # Convert monthly to yearly
    sal_min_yr = salary_min  if salary_min is not None else None
    sal_max_yr = salary_max  if salary_max is not None else None

    if sal_min_yr is not None and sal_max_yr is not None:
        return f"{currency_prefix}{sal_min_yr} - {currency_prefix}{sal_max_yr}/year"
    if sal_min_yr is not None:
        return f"{currency_prefix}{sal_min_yr}+/year"
    return f"Up to {currency_prefix}{sal_max_yr}/year"


def _build_location_label(city: Optional[str], state: Optional[str], country: Optional[str]) -> Optional[str]:
    parts = [part for part in [city, state, country] if part]
    return ", ".join(parts) if parts else None


def _build_sponsorship_label(job) -> Optional[str]:
    if job.visa_statuses:
        return ", ".join(vs.name for vs in job.visa_statuses)
    if job.visa_status:
        return job.visa_status.name
    return None



def _build_status_label(status: str, deadline: Optional[datetime]) -> str:
    status_lower = status.lower() if status else "draft"
    if status_lower == "draft":
        return "drafted"
    elif status_lower == "closed":
        return "closed"
    elif status_lower == "published":
        if deadline:
            now = datetime.now(deadline.tzinfo or timezone.utc)
            if now > deadline:
                return "expired"
        return "published"
    return status_lower


@router.get("/dashboard", response_model=List[JobDashboardCardResponse])
def get_dashboard_jobs(
    search: Optional[str] = Query(None),
    work_type: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    match_score: Optional[str] = Query(None),
    job_post_date: Optional[str] = Query(None),
    salary_min: Optional[int] = Query(None),
    salary_max: Optional[int] = Query(None),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_active_user),
):
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
            joinedload(JobPosting.visa_statuses),
        )
        .filter(JobPosting.is_active == True, JobPosting.status == JobStatus.PUBLISHED)
    )

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
        from app.models.meta import MetaWorkMode
        query = query.join(JobPosting.work_mode).filter(func.lower(MetaWorkMode.name) == work_type.lower())

    # Apply job type filter
    if job_type and job_type.lower() != "all":
        from app.models.meta import MetaEmploymentType
        norm_jt = job_type.replace("-", "_").lower()
        query = query.join(JobPosting.employment_type).filter(func.lower(MetaEmploymentType.name) == norm_jt)

    # Apply location country filter
    if location and location.lower() != "all":
        from app.models.meta import MetaCountry
        if location.lower() in ("u.s.", "us", "united states"):
            query = query.join(JobPosting.country).filter(func.upper(MetaCountry.iso_code) == "US")
        elif location.lower() in ("india", "in"):
            query = query.join(JobPosting.country).filter(func.upper(MetaCountry.iso_code) == "IN")

    # Apply salary filters
    if salary_min is not None:
        query = query.filter(JobPosting.salary_min >= salary_min)
    if salary_max is not None:
        query = query.filter(JobPosting.salary_max <= salary_max)

    # Apply job post date filter
    if job_post_date:
        now = datetime.now(timezone.utc)
        if job_post_date.lower() in ("today", "within 24 hour"):
            query = query.filter(JobPosting.created_at >= now - timedelta(days=1))
        elif job_post_date.lower() == "last 7 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=7))
        elif job_post_date.lower() == "last 30 days":
            query = query.filter(JobPosting.created_at >= now - timedelta(days=30))

    # Retrieve candidate details to compute ai match scores
    candidate = None
    primary_resume = None
    matching_service = None
    if current_user and current_user.role == UserRole.CANDIDATE:
        candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
        if candidate:
            primary_resume = db.query(Resume).filter(
                Resume.candidate_id == candidate.id,
                Resume.is_primary == True
            ).first()
            matching_service = MatchingEngine(db)

    # Fetch jobs. If match_score filter is active, fetch all first.
    # Otherwise, apply SQL pagination.
    if match_score and match_score.lower() != "all":
        jobs = query.order_by(JobPosting.created_at.desc()).all()
    else:
        jobs = query.order_by(JobPosting.created_at.desc()).offset(skip).limit(limit).all()

    # Get saved and applied job details
    saved_job_ids = set()
    applied_job_ids = set()
    if candidate and jobs:
        job_ids = [job.id for job in jobs]
        saved_jobs = db.query(SavedJob.job_id).filter(
            SavedJob.candidate_id == candidate.id,
            SavedJob.job_id.in_(job_ids)
        ).all()
        saved_job_ids = {r[0] for r in saved_jobs}

        applied_jobs = db.query(JobApplication.job_id).filter(
            JobApplication.candidate_id == candidate.id,
            JobApplication.job_id.in_(job_ids)
        ).all()
        applied_job_ids = {r[0] for r in applied_jobs}

    response = []
    for job in jobs:
        # Calculate AI match score
        ai_score = 0
        if primary_resume and primary_resume.overall_embedding is not None and matching_service:
            try:
                score_details = matching_service.score_resume_object_for_job_object(primary_resume, job)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0
        else:
            ai_score = job.ai_score_threshold or 0

        # Filter by Match Score in Python if specified
        if match_score and match_score.lower() != "all":
            normalized_score = match_score.replace("–", "-").strip()
            if normalized_score == "90%+" and ai_score < 90:
                continue
            elif normalized_score == "80 - 89%" and not (80 <= ai_score <= 89):
                continue
            elif normalized_score == "70 - 79%" and not (70 <= ai_score <= 79):
                continue
            elif normalized_score == "Below 70%" and ai_score >= 70:
                continue

        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None

        is_saved = job.id in saved_job_ids
        is_applied = job.id in applied_job_ids

        response.append(
            JobDashboardCardResponse(
                id=job.id,
                company_id=job.company_id,
                company_name=job.company.name if job.company else None,
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
                company_verified=None,
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
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_currency_code=currency_code,
                salary_currency_symbol=currency_symbol,
                salary_range_label=_format_salary_range(
                    job.salary_min,
                    job.salary_max,
                    currency_symbol,
                    currency_code,
                ),
                employment_type=job.employment_type.name if job.employment_type else None,
                save_action="unsave" if is_saved else "save",
                apply_action="applied" if is_applied else "apply",
            )
        )

    # Perform Python-level pagination if match_score filter was applied
    if match_score and match_score.lower() != "all":
        return response[skip : skip + limit]

    return response


@job_flow_router.post("/create-a-job/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_a_job(
    job_in: JobCreateBasic,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Step 1: Create a basic job posting draft and generate a job_id.
    """
    if not current_user.employer or not current_user.employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer must create or join a company before posting a job."
        )
    
    job_data = job_in.model_dump()
    days_deadline = job_data.pop("application_deadline", None)
    visa_sponsorship_ids = job_data.pop("visa_sponsorship_ids", None)
    
    deadline_date = None
    if days_deadline is not None:
        deadline_date = datetime.now(timezone.utc) + timedelta(days=days_deadline)

    # Backwards compatibility: set requires_visa_sponsorship to first ID if list is provided
    if visa_sponsorship_ids:
        job_data["requires_visa_sponsorship"] = visa_sponsorship_ids[0]

    db_job = JobPosting(
        **job_data,
        application_deadline=deadline_date,
        company_id=current_user.employer.company_id,
        status=JobStatus.DRAFT,
        is_active=False,
        start_date=datetime.now(timezone.utc)
    )
    
    if visa_sponsorship_ids:
        from app.models.meta import MetaVisaStatus
        meta_visas = db.query(MetaVisaStatus).filter(MetaVisaStatus.id.in_(visa_sponsorship_ids)).all()
        db_job.visa_statuses = meta_visas

    if db_job.city_id:
        from app.models.meta import MetaCity
        city = db.query(MetaCity).filter(MetaCity.id == db_job.city_id).first()
        if city:
            db_job.state_id = city.state_id
            db_job.country_id = city.country_id
    
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job


@job_flow_router.put("/{job_id}/about-job/", response_model=JobResponse)
def update_about_job(
    job_id: UUID,
    job_in: JobAboutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Step 2: Update the record about the role, responsibilities, benefits, and job overview.
    """
    db_job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not db_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
    
    if not current_user.employer or db_job.company_id != current_user.employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this job posting."
        )
        
    update_data = job_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_job, field, value)
        
    db.commit()
    db.refresh(db_job)
    return db_job


@job_flow_router.put("/{job_id}/work-authorization", response_model=JobResponse)
def update_work_authorization(
    job_id: UUID,
    job_in: JobWorkAuthorizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Step 3: Update work authorization requirements and the candidate match score threshold.
    """
    db_job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not db_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
    
    if not current_user.employer or db_job.company_id != current_user.employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this job posting."
        )
        
    update_data = job_in.model_dump(exclude_unset=True)
    visa_sponsorship_ids = update_data.pop("visa_sponsorship_ids", None)
    
    if visa_sponsorship_ids is not None:
        from app.models.meta import MetaVisaStatus
        meta_visas = db.query(MetaVisaStatus).filter(MetaVisaStatus.id.in_(visa_sponsorship_ids)).all()
        db_job.visa_statuses = meta_visas
        db_job.requires_visa_sponsorship = visa_sponsorship_ids[0] if visa_sponsorship_ids else None

    for field, value in update_data.items():
        setattr(db_job, field, value)
        
    db.commit()
    db.refresh(db_job)
    return db_job


@job_flow_router.put("/{job_id}/cover-letter", response_model=JobResponse)
def update_cover_letter_config(
    job_id: UUID,
    job_in: JobCoverLetterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Step 4: Update cover letter requirements configuration.
    """
    db_job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not db_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
    
    if not current_user.employer or db_job.company_id != current_user.employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this job posting."
        )
        
    update_data = job_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_job, field, value)
        
    db.commit()
    db.refresh(db_job)
    return db_job


@job_flow_router.get("/{job_id}/preview", response_model=JobResponse)
def get_job_preview(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Step 5: Get a preview of the job posting.
    """
    db_job = (
        db.query(JobPosting)
        .options(
            joinedload(JobPosting.taxonomy_job_role),
            joinedload(JobPosting.employment_type),
            joinedload(JobPosting.work_mode),
            joinedload(JobPosting.city),
            joinedload(JobPosting.state),
            joinedload(JobPosting.country),
            joinedload(JobPosting.currency),
            joinedload(JobPosting.visa_status),
            joinedload(JobPosting.visa_statuses)
        )
        .filter(JobPosting.id == job_id)
        .first()
    )
    if not db_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
    
    if not current_user.employer or db_job.company_id != current_user.employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to preview this job posting."
        )
        
    return db_job


@job_flow_router.put("/{job_id}/publish", response_model=JobResponse)
def publish_job_final(
    job_id: UUID,
    job_in: JobPublishUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Step 6: Publish the job (status = "published") or save it back to "draft".
    """
    db_job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not db_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )
    
    if not current_user.employer or db_job.company_id != current_user.employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to publish this job posting."
        )
        
    # Validate critical required fields before publishing
    if job_in.status == JobStatus.PUBLISHED:
        if not db_job.title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job title is required to publish."
            )
            
        # Check company plan posting limit
        if db_job.status != JobStatus.PUBLISHED:
            db_job.created_at = datetime.now(timezone.utc)
            company = db.query(Company).filter(Company.id == db_job.company_id).first()
            if company:
                tier = company.plan_tier or "free"
                limits = POSTER_PLAN_LIMITS.get_limits(tier, db)
                if limits["is_lifetime_cap"]:
                    # Count total published/closed jobs created for the company (excluding drafts)
                    published_jobs = db.query(JobPosting).filter(
                        JobPosting.company_id == company.id,
                        JobPosting.status.in_([JobStatus.PUBLISHED, JobStatus.CLOSED]),
                        JobPosting.id != db_job.id
                    ).count()
                    if published_jobs >= limits["job_postings_limit"]:
                        raise HTTPException(
                            status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail=f"You have reached your lifetime job posting limit of {limits['job_postings_limit']} for the {limits['name']} plan. Please upgrade to post more."
                        )
                else:
                    # Count active job postings (status == JobStatus.PUBLISHED)
                    active_jobs = db.query(JobPosting).filter(
                        JobPosting.company_id == company.id,
                        JobPosting.status == JobStatus.PUBLISHED,
                        JobPosting.id != db_job.id
                    ).count()
                    if active_jobs >= limits["job_postings_limit"]:
                        raise HTTPException(
                            status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            detail=f"You have reached your active job posting limit of {limits['job_postings_limit']} for the {limits['name']} plan. Close or archive an active job to publish a new one."
                        )
                        
        db_job.status = JobStatus.PUBLISHED
        db_job.is_active = True
    else:
        db_job.status = JobStatus.DRAFT
        db_job.is_active = False
        
    db.commit()
    db.refresh(db_job)
    return db_job


@router.get("/dashboard/overview", response_model=JobPosterDashboardResponse)
def get_employer_dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> JobPosterDashboardResponse:
    """
    Get consolidated metrics, pipeline funnel, hires by domain, recent actions, and job status overview
    for the authenticated employer's company.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # 1. KPIs
    total_jobs = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.PUBLISHED
    ).count()

    total_applicants = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(JobPosting.company_id == company_id)
        .count()
    )

    total_interviews = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(
            JobPosting.company_id == company_id,
            JobApplication.status.in_(["interviewing", "interviewed"])
        )
        .count()
    )

    total_hired = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(
            JobPosting.company_id == company_id,
            JobApplication.status.in_(["offered", "hired"])
        )
        .count()
    )

    # 2. Monthly Success Rate (Trend)
    # Fetch all applications for the company to aggregate in Python (fully DB independent)
    all_apps = (
        db.query(JobApplication.created_at, JobApplication.status)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(JobPosting.company_id == company_id)
        .all()
    )

    now = datetime.now(timezone.utc)
    months_list = []
    for i in range(5, -1, -1):
        target_date = now - timedelta(days=i*30)
        months_list.append((target_date.year, target_date.month, target_date.strftime("%b")))

    monthly_success_rate = []

    for year, month_num, month_name in months_list:
        total_in_month = sum(
            1 for (created_at, _) in all_apps
            if created_at.year == year and created_at.month == month_num
        )
        hired_in_month = sum(
            1 for (created_at, status) in all_apps
            if created_at.year == year and created_at.month == month_num and status in ["offered", "hired"]
        )
        
        rate = 0.0
        if total_in_month > 0:
            rate = round((hired_in_month / total_in_month) * 100, 2)
        
        monthly_success_rate.append(
            MonthlySuccessRatePoint(
                month=month_name,
                rate=rate
            )
        )

    # 3. Candidates Hired By Domain
    from app.models.taxonomy import TaxonomyDomain
    
    # Get all domains associated with the company's job postings to show all active domains on UI chart
    company_domains = (
        db.query(TaxonomyDomain.name)
        .join(JobPosting, JobPosting.taxonomy_domain_id == TaxonomyDomain.id)
        .filter(JobPosting.company_id == company_id)
        .distinct()
        .all()
    )
    
    domain_query = (
        db.query(TaxonomyDomain.name, func.count(JobApplication.id))
        .join(JobPosting, JobPosting.taxonomy_domain_id == TaxonomyDomain.id)
        .join(JobApplication, JobApplication.job_id == JobPosting.id)
        .filter(
            JobPosting.company_id == company_id,
            JobApplication.status.in_(["offered", "hired"])
        )
        .group_by(TaxonomyDomain.name)
        .all()
    )

    domain_counts = {name: 0 for (name,) in company_domains if name}
    for name, count in domain_query:
        if name:
            domain_counts[name] = count

    hires_by_domain = [
        HiresByDomainPoint(
            domain=name,
            count=count
        )
        for name, count in domain_counts.items()
    ]

    # 4. Recent Action Feed
    action_feed = []
    
    pending_apps = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(JobPosting.company_id == company_id, JobApplication.status == "applied")
        .order_by(JobApplication.created_at.desc())
        .limit(5)
        .all()
    )

    feed_id_counter = 1
    for app in pending_apps:
        action_feed.append(
            ActionFeedItem(
                id=f"act-{feed_id_counter}",
                type="action_required",
                title="Hiring action required",
                description=f"Candidate applied for {app.job.title}. Pending decision is waiting.",
                created_at=app.created_at,
                icon="target"
            )
        )
        feed_id_counter += 1

    draft_jobs = (
        db.query(JobPosting)
        .filter(JobPosting.company_id == company_id, JobPosting.status == JobStatus.DRAFT)
        .order_by(JobPosting.updated_at.desc())
        .limit(2)
        .all()
    )

    for dj in draft_jobs:
        if len(action_feed) >= 5:
            break
        action_feed.append(
            ActionFeedItem(
                id=f"act-{feed_id_counter}",
                type="warning",
                title="Complete draft job posting",
                description=f"Draft post '{dj.title}' was updated. Revise skills for today's market.",
                created_at=dj.updated_at,
                icon="alert-circle"
            )
        )
        feed_id_counter += 1

    # 5. Hiring Funnel
    app_count = total_applicants
    
    ai_shortlist_count = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(
            JobPosting.company_id == company_id,
            JobApplication.status.in_(["under_review", "shortlisted"])
        )
        .count()
    )

    interview_count = total_interviews

    onhold_count = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(
            JobPosting.company_id == company_id,
            JobApplication.status == "onhold"
        )
        .count()
    )

    hired_count = total_hired

    rejected_count = (
        db.query(JobApplication)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(
            JobPosting.company_id == company_id,
            JobApplication.status == "rejected"
        )
        .count()
    )

    hiring_funnel = [
        FunnelStagePoint(stage="Application", count=app_count),
        FunnelStagePoint(stage="AI Shortlisted", count=ai_shortlist_count),
        FunnelStagePoint(stage="Interview", count=interview_count),
        FunnelStagePoint(stage="Onhold", count=onhold_count),
        FunnelStagePoint(stage="Hired", count=hired_count),
        FunnelStagePoint(stage="Rejected", count=rejected_count)
    ]

    # 6. Job Post Status Overview
    active_posts = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.PUBLISHED,
        JobPosting.is_active == True
    ).count()

    draft_posts = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.DRAFT
    ).count()

    closed_posts = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.CLOSED
    ).count()

    total_visitors = (active_posts * 10) + (closed_posts * 5)

    job_status_overview = JobStatusBreakdown(
        active_posts=active_posts,
        draft_posts=draft_posts,
        closed_posts=closed_posts,
        total_visitors=total_visitors
    )

    return JobPosterDashboardResponse(
        kpis=JobPosterDashboardKPIs(
            total_jobs=total_jobs,
            total_applicants=total_applicants,
            total_interviews=total_interviews,
            total_hired=total_hired
        ),
        monthly_success_rate=monthly_success_rate,
        hires_by_domain=hires_by_domain,
        action_feed=action_feed,
        hiring_funnel=hiring_funnel,
        job_status_overview=job_status_overview
    )


@router.get("/jobs", response_model=List[EmployerJobListingItem])
def get_employer_jobs(
    job_status: Optional[str] = Query("all", alias="status"),
    search: Optional[str] = Query(None),
    viewed: Optional[bool] = Query(None, description="Filter jobs by whether they have candidates with the specified viewed status"),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> List[EmployerJobListingItem]:
    """
    Get all jobs posted by the employer's company, matching the layout in the UI screenshots.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    query = (
        db.query(JobPosting)
        .options(
            joinedload(JobPosting.city),
            joinedload(JobPosting.state),
            joinedload(JobPosting.country),
            joinedload(JobPosting.work_mode),
            joinedload(JobPosting.company),
            joinedload(JobPosting.visa_statuses)
        )
        .filter(JobPosting.company_id == company_id)
    )

    if job_status and job_status.lower() != "all":
        status_val = job_status.lower()
        if status_val in ("active", "active-jobs", "published"):
            status_val = "published"
        query = query.filter(JobPosting.status == status_val)

    if search:
        query = query.filter(
            or_(
                JobPosting.title.ilike(f"%{search}%"),
                JobPosting.description.ilike(f"%{search}%")
            )
        )

    if viewed is not None:
        query = query.filter(
            db.query(JobApplication.id)
            .filter(JobApplication.job_id == JobPosting.id)
            .filter(JobApplication.is_viewed == viewed)
            .exists()
        )

    jobs = query.order_by(JobPosting.created_at.desc()).offset(skip).limit(limit).all()

    # Pre-fetch counts for all jobs to optimize
    job_ids = [job.id for job in jobs]
    
    # New applicants counts (status == "applied")
    new_app_counts = {}
    if job_ids:
        new_app_query = (
            db.query(JobApplication.job_id, func.count(JobApplication.id))
            .filter(
                JobApplication.job_id.in_(job_ids),
                JobApplication.status == "applied"
            )
            .group_by(JobApplication.job_id)
            .all()
        )
        new_app_counts = {jid: cnt for jid, cnt in new_app_query}

    # Shortlisted counts (status in ["under_review", "shortlisted"])
    shortlisted_counts = {}
    if job_ids:
        shortlist_query = (
            db.query(JobApplication.job_id, func.count(JobApplication.id))
            .filter(
                JobApplication.job_id.in_(job_ids),
                JobApplication.status.in_(["under_review", "shortlisted"])
            )
            .group_by(JobApplication.job_id)
            .all()
        )
        shortlisted_counts = {jid: cnt for jid, cnt in shortlist_query}

    response = []
    for job in jobs:
        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None

        # Build Work Modes tags
        work_modes = []
        if job.work_mode:
            work_modes.append(job.work_mode.name)
            
        # Build Visa Sponsorship tags
        visa_sponsorships = []
        if job.visa_statuses:
            visa_sponsorships.extend(vs.name for vs in job.visa_statuses)
        elif job.visa_status:
            visa_sponsorships.append(job.visa_status.name)
        elif job.us_citizen_or_pr_only:
            visa_sponsorships.append("US Citizen or PR only")
        else:
            visa_sponsorships.append("Visa sponsorship")

        deadline_str = None
        if job.application_deadline:
            deadline_str = job.application_deadline.strftime("%d %b")

        response.append(
            EmployerJobListingItem(
                id=job.id,
                company_name=job.company.name if job.company else "Company",
                company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
                company_verified=True,
                job_title=job.title,
                ai_score_threshold=job.ai_score_threshold or 0,
                work_modes_list=work_modes,
                visa_sponsorships_list=visa_sponsorships,
                location_label=_build_location_label(city_name, state_name, country_name),
                posted_ago=_format_posted_ago(job.created_at),
                new_applicants_count=new_app_counts.get(job.id, 0),
                shortlisted_count=shortlisted_counts.get(job.id, 0),
                deadline_label=deadline_str,
                status=job.status,
                status_label=_build_status_label(job.status, job.application_deadline),
                is_valid=job.is_valid,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                currency_id=job.currency_id
            )
        )

    return response


@router.get("/jobs/stats", response_model=JobPosterJobsStatsResponse)
def get_employer_jobs_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer)
) -> JobPosterJobsStatsResponse:
    """
    Get job statistics (active, closed, draft, expired counts) for the employer's company.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    now = datetime.now(timezone.utc)

    # Expired: published and past the deadline
    expired = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.PUBLISHED,
        JobPosting.application_deadline.isnot(None),
        JobPosting.application_deadline < now
    ).count()

    # Active: published and (no deadline or not past deadline)
    active = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.PUBLISHED,
        or_(
            JobPosting.application_deadline.is_(None),
            JobPosting.application_deadline >= now
        )
    ).count()

    draft = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.DRAFT
    ).count()

    closed = db.query(JobPosting).filter(
        JobPosting.company_id == company_id,
        JobPosting.status == JobStatus.CLOSED
    ).count()

    return JobPosterJobsStatsResponse(
        active=active,
        closed=closed,
        draft=draft,
        expired=expired
    )


@router.post("/jobs/save-draft", response_model=JobResponse)
def save_new_job_draft(
    job_in: JobSaveDraft,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> JobResponse:
    """
    Create a new job posting with draft status, generating a new job_id.
    """
    import uuid
    new_job_id = uuid.uuid4()
    return save_job_draft(job_id=new_job_id, job_in=job_in, db=db, current_user=current_user)


@router.patch("/jobs/{job_id}/save-draft", response_model=JobResponse)
@router.post("/jobs/{job_id}/save-draft", response_model=JobResponse)
def save_job_draft(
    job_id: UUID,
    job_in: JobSaveDraft,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> JobResponse:
    """
    Create a new job posting or update an existing one with draft status, using the specified job_id.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # Check if job posting exists
    db_job = db.query(JobPosting).filter(JobPosting.id == job_id).first()

    job_data = job_in.model_dump(exclude_unset=True)
    days_deadline = job_data.pop("application_deadline", None)
    visa_sponsorship_ids = job_data.pop("visa_sponsorship_ids", None)
    
    # Resolve job role if title is a digit representing the ID
    taxonomy_job_role_id = None
    role_resolved = False
    if "title" in job_data:
        title_val = job_data["title"]
        if title_val and title_val.isdigit():
            from app.models.taxonomy import TaxonomyJobRole
            job_role_id = int(title_val)
            job_role = db.query(TaxonomyJobRole).filter(TaxonomyJobRole.id == job_role_id).first()
            if not job_role:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Taxonomy job role with ID {job_role_id} not found."
                )
            job_data["title"] = job_role.name
            taxonomy_job_role_id = job_role_id
            role_resolved = True
            if job_role.domain_id:
                job_data["taxonomy_domain_id"] = job_role.domain_id
        else:
            # Custom text title, reset taxonomy job role
            taxonomy_job_role_id = None
            role_resolved = True

    deadline_date = None
    if days_deadline is not None:
        deadline_date = datetime.now(timezone.utc) + timedelta(days=days_deadline)

    if db_job:
        # Verify ownership
        if db_job.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update this job posting."
            )
        
        # Handle visa_sponsorship_ids update safely
        if visa_sponsorship_ids is not None:
            if not db_job.visa_statuses or (isinstance(visa_sponsorship_ids, list) and len(visa_sponsorship_ids) > 0):
                from app.models.meta import MetaVisaStatus
                meta_visas = db.query(MetaVisaStatus).filter(MetaVisaStatus.id.in_(visa_sponsorship_ids)).all()
                db_job.visa_statuses = meta_visas
                db_job.requires_visa_sponsorship = visa_sponsorship_ids[0] if visa_sponsorship_ids else None

        # Update existing job posting safely (do not overwrite with empty/default values if we already have data)
        for field, value in job_data.items():
            existing_value = getattr(db_job, field)
            if existing_value is not None:
                # Ignore null/empty/zero values from the patch if database already has valid data
                if value is None:
                    continue
                if isinstance(existing_value, str) and existing_value != "" and value == "":
                    continue
                if isinstance(existing_value, int) and not isinstance(existing_value, bool) and existing_value != 0 and value == 0:
                    continue
                if isinstance(existing_value, list) and len(existing_value) > 0 and (value is None or (isinstance(value, list) and len(value) == 0)):
                    continue
            setattr(db_job, field, value)
            
        if days_deadline is not None:
            db_job.application_deadline = deadline_date
            
        if role_resolved:
            db_job.taxonomy_job_role_id = taxonomy_job_role_id

        db_job.status = JobStatus.DRAFT
        db_job.is_active = False
    else:
        # Create new job posting with client-specified ID
        if "title" not in job_data or job_data["title"] is None:
            job_data["title"] = "Untitled"
            
        db_job = JobPosting(
            id=job_id,
            company_id=company_id,
            status=JobStatus.DRAFT,
            is_active=False,
            start_date=datetime.now(timezone.utc),
            application_deadline=deadline_date,
            taxonomy_job_role_id=taxonomy_job_role_id,
            **job_data
        )
        if visa_sponsorship_ids:
            from app.models.meta import MetaVisaStatus
            meta_visas = db.query(MetaVisaStatus).filter(MetaVisaStatus.id.in_(visa_sponsorship_ids)).all()
            db_job.visa_statuses = meta_visas
            db_job.requires_visa_sponsorship = visa_sponsorship_ids[0]
        db.add(db_job)

    # Resolve location state and country if city_id is modified
    if db_job.city_id:
        from app.models.meta import MetaCity
        city = db.query(MetaCity).filter(MetaCity.id == db_job.city_id).first()
        if city:
            db_job.state_id = city.state_id
            db_job.country_id = city.country_id

    db.commit()
    db.refresh(db_job)
    return db_job


@router.get("/jobs/{job_id}", response_model=EmployerJobDetailResponse)
def get_employer_job_detail(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> EmployerJobDetailResponse:
    """
    Get detailed view of a job posted by the employer's company, including pipeline summary.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    job = db.query(JobPosting).options(
        joinedload(JobPosting.visa_status),
        joinedload(JobPosting.visa_statuses),
        joinedload(JobPosting.employment_type)
    ).filter(
        JobPosting.id == job_id,
        JobPosting.company_id == company_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    # Calculate applicant counts for each stage
    stage_counts = (
        db.query(JobApplication.status, func.count(JobApplication.id))
        .filter(JobApplication.job_id == job_id)
        .group_by(JobApplication.status)
        .all()
    )
    counts_map = {status: count for status, count in stage_counts}

    applied = counts_map.get("applied", 0)
    shortlisted = counts_map.get("under_review", 0) + counts_map.get("shortlisted", 0)
    interview = counts_map.get("interviewing", 0) + counts_map.get("interviewed", 0)
    onhold = counts_map.get("onhold", 0)
    hired = counts_map.get("hired", 0) + counts_map.get("offered", 0)
    rejected = counts_map.get("rejected", 0)

    pipeline_summary = PipelineStageSummary(
        applied=applied,
        shortlisted=shortlisted,
        interview=interview,
        onhold=onhold,
        hired=hired,
        rejected=rejected
    )

    # Build work modes & visa lists
    work_modes = []
    if job.work_mode:
        work_modes.append(job.work_mode.name)
    visa_sponsorships = []
    if job.visa_statuses:
        visa_sponsorships.extend(vs.name for vs in job.visa_statuses)
    elif job.visa_status:
        visa_sponsorships.append(job.visa_status.name)
    elif job.us_citizen_or_pr_only:
        visa_sponsorships.append("US Citizen or PR only")
    else:
        visa_sponsorships.append("Visa sponsorship")

    city_name = job.city.name if job.city else None
    state_name = job.state.name if job.state else None
    country_name = job.country.name if job.country else None
    
    deadline_str = None
    if job.application_deadline:
        deadline_str = job.application_deadline.strftime("%d %b")

    company_loc = None
    if job.company:
        comp_city = job.company.city.name if job.company.city else None
        comp_state = job.company.state.name if job.company.state else None
        comp_country = job.company.country.name if job.company.country else None
        company_loc = _build_location_label(comp_city, comp_state, comp_country)

    company_details = EmployerCompanyDetails(
        name=job.company.name if job.company else "Company",
        website=job.company.website if job.company else None,
        logo_url=s3_service.get_presigned_url(job.company.logo_url) if (job.company and job.company.logo_url) else None,
        founded_year=job.company.founded_year if job.company else None,
        description=job.company.description if job.company else None,
        location=company_loc,
        company_size=job.company.size.label if (job.company and job.company.size) else None
    )

    return EmployerJobDetailResponse(
        id=job.id,
        company_name=job.company.name if job.company else "Company",
        company_logo_url=s3_service.get_presigned_url(job.company.logo_url) if job.company else None,
        company_verified=True,
        company_size=job.company.size.label if (job.company and job.company.size) else None,
        job_title=job.title,
        ai_score_threshold=job.ai_score_threshold or 0,
        num_positions=job.num_positions,
        work_modes_list=work_modes,
        visa_sponsorships_list=visa_sponsorships,
        location_label=_build_location_label(city_name, state_name, country_name),
        posted_ago=_format_posted_ago(job.created_at),
        new_applicants_count=applied,
        shortlisted_count=shortlisted,
        deadline_label=deadline_str,
        status=job.is_valid,
        status_label=_build_status_label(job.status, job.application_deadline),
        salary_min=job.salary_min if job.salary_min is not None else None,
        salary_max=job.salary_max if job.salary_max is not None else None,
        salary_range_label=_format_salary_range(job.salary_min, job.salary_max, job.currency.symbol if job.currency else None, job.currency.code if job.currency else None),
        is_valid=job.is_valid,
        experience=_format_experience_label(job.min_experience_years, job.max_experience_years),
        employment_type=job.employment_type.name if job.employment_type else None,
        deadline=job.application_deadline,
        Deadline=deadline_str,
        Employment_Type=job.employment_type.name if job.employment_type else None,
        pipeline_summary=pipeline_summary,
        job_overview=job.job_overview,
        about_role=job.about_role,
        requirements=job.requirements,
        responsibilities=job.responsibilities,
        benefits=job.benefits,
        company_details=company_details
    )


@router.get("/jobs/{job_id}/stats", response_model=JobCandidateStatsResponse)
def get_employer_job_candidate_stats(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> JobCandidateStatsResponse:
    """
    Get statistics (application, shortlisted, hired, onhold, reject counts) for a specific job posting.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # Verify job posting exists and belongs to the employer's company
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.company_id == company_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    # Calculate applicant counts for each stage
    stage_counts = (
        db.query(JobApplication.status, func.count(JobApplication.id))
        .filter(JobApplication.job_id == job_id)
        .group_by(JobApplication.status)
        .all()
    )
    counts_map = {status: count for status, count in stage_counts}

    application = sum(counts_map.values())
    shortlisted = counts_map.get("under_review", 0) + counts_map.get("shortlisted", 0)
    interview= counts_map.get("interviewing",0)
    onhold = counts_map.get("onhold", 0)
    hired = counts_map.get("hired", 0) + counts_map.get("offered", 0)
    reject = counts_map.get("rejected", 0)

    return JobCandidateStatsResponse(
        application=application,
        shortlisted=shortlisted,
        interview=interview,
        hired=hired,
        onhold=onhold,
        reject=reject
    )


@router.get("/jobs/{job_id}/applicants", response_model=List[JobPosterApplicantListItem])
def list_job_applicants(
    job_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status (applied, shortlisted, interview, onhold, hired, rejected)"),
    work_mode: Optional[str] = Query(None, description="Filter by work mode (Remote, Hybrid, Onsite)"),
    job_type: Optional[str] = Query(None, description="Filter by job type (Full-Time, Internship, Contract)"),
    location: Optional[str] = Query(None, description="Filter by location (e.g. India, U.S.)"),
    match_score: Optional[str] = Query(None, description="Filter by match score range (90%+, 80-89%, 70-79%, Below 70%)"),
    min_experience: Optional[int] = Query(None, description="Minimum experience in years"),
    max_experience: Optional[int] = Query(None, description="Maximum experience in years"),
    viewed: Optional[bool] = Query(None, description="Filter by viewed status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer)
) -> List[JobPosterApplicantListItem]:
    """
    List all candidates who applied to a specific job posting with filters.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=400,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # Verify job posting exists and belongs to employer's company
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.company_id == company_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job posting not found."
        )

    # Base query for JobApplication
    query = db.query(JobApplication).filter(JobApplication.job_id == job_id)

    # Filter by viewed status
    if viewed is not None:
        query = query.filter(JobApplication.is_viewed == viewed)

    # Filter by application status
    if status and status.lower() != "all":
        status_lower = status.lower()
        if status_lower == "applications" or status_lower == "applied":
            # Keep all candidates in the "applied"/"applications" list permanently
            # regardless of their current status (do not filter by status)
            pass
        elif status_lower == "shortlisted":
            query = query.filter(JobApplication.status.in_(["under_review", "shortlisted"]))
        elif status_lower == "interview":
            query = query.filter(JobApplication.status.in_(["interviewing", "interviewed"]))
        elif status_lower == "onhold":
            query = query.filter(JobApplication.status == "onhold")
        elif status_lower == "hired":
            query = query.filter(JobApplication.status.in_(["offered", "hired"]))
        elif status_lower == "rejected":
            query = query.filter(JobApplication.status == "rejected")
        else:
            # Fallback to direct string match
            query = query.filter(JobApplication.status == status_lower)

    # Load candidate and user relationships for filtering
    query = query.join(Candidate, JobApplication.candidate_id == Candidate.id)

    # Filter by candidate's preferred location (work mode / location filters)
    if work_mode and work_mode.lower() != "all":
        wm = work_mode.lower()
        query = query.filter(Candidate.pref_locations.ilike(f"%{wm}%"))

    if job_type and job_type.lower() != "all":
        jt = job_type.lower()
        query = query.filter(Candidate.pref_role_type.ilike(f"%{jt}%"))

    if location and location.lower() != "all":
        loc = location.lower()
        query = query.filter(Candidate.pref_locations.ilike(f"%{loc}%"))

    # Fetch applicants
    applications = query.order_by(JobApplication.created_at.desc()).all()

    matching_service = MatchingEngine(db)
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    response = []

    for app in applications:
        candidate = app.candidate
        if not candidate:
            continue

        # Resolve the resume used (job-specific or primary)
        resume = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.job_id == job_id,
            Resume.is_deleted == False
        ).order_by(Resume.is_ai_optimized.desc(), Resume.updated_at.desc()).first()
        if not resume:
            resume = db.query(Resume).filter(
                Resume.candidate_id == candidate.id,
                Resume.is_primary == True,
                Resume.is_deleted == False
            ).first()

        # Calculate AI match score
        ai_score = 0
        if resume and resume.overall_embedding is not None and job:
            try:
                score_details = matching_service.score_resume_object_for_job_object(resume, job)
                ai_score = int(score_details["final_score"])
            except Exception:
                ai_score = 0

        # Filter by Match Score in Python
        if match_score and match_score.lower() != "all":
            ms_clean = match_score.replace(" ", "")
            if ms_clean == "90%+" and ai_score < 90:
                continue
            elif (ms_clean == "80-89%" or ms_clean == "80–89%") and not (80 <= ai_score <= 89):
                continue
            elif (ms_clean == "70-79%" or ms_clean == "70–79%") and not (70 <= ai_score <= 79):
                continue
            elif ms_clean == "Below70%" and ai_score >= 70:
                continue

        # Filter by Experience years
        exp_years = resume.total_experience_years if resume else 0
        if min_experience is not None and exp_years < min_experience:
            continue
        if max_experience is not None and exp_years > max_experience:
            continue

        # Format salary range label if candidate specifies pref_min_salary
        salary_range_label = None
        if candidate.pref_min_salary is not None:
            min_salary_k = candidate.pref_min_salary // 1000
            salary_range_label = f"${min_salary_k}k - ${min_salary_k + 10}k /month"

        # Format location or role name
        role = candidate.taxonomy_domain.name if candidate.taxonomy_domain else None

        response.append(
            JobPosterApplicantListItem(
                id=candidate.id,
                full_name=candidate.full_name,
                profile_picture=s3_service.get_presigned_url(candidate.profile_picture) if candidate.profile_picture else None,
                is_verified=candidate.user.is_verified if candidate.user else False,
                role=role,
                ai_score=ai_score,
                experience_years=exp_years,
                salary_range_label=salary_range_label,
                employment_type=candidate.pref_role_type,
                status=app.status,
                applied_date=app.created_at,
                is_viewed=app.is_viewed,
                rejected_from=app.rejected_from,
                rejected_at=app.rejected_at
            )
        )

    return response


@router.get("/jobs/{job_id}/applicants/{candidate_id}", response_model=JobPosterApplicantProfileResponse)
def get_applicant_profile(
    job_id: UUID,
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer)
) -> JobPosterApplicantProfileResponse:
    """
    Get the detailed candidate profile for a specific job application,
    including the resume used while applying, the cover letter, summary, and timeline.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=400,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # Verify job posting exists and belongs to employer's company
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.company_id == company_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job posting not found."
        )

    # Verify the application exists
    app = db.query(JobApplication).filter(
        JobApplication.job_id == job_id,
        JobApplication.candidate_id == candidate_id
    ).first()

    if not app:
        raise HTTPException(
            status_code=404,
            detail="Application for this candidate on this job was not found."
        )

    trigger_view_notification = False
    if not app.is_viewed:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company:
            tier = company.plan_tier or "free"
            limits = POSTER_PLAN_LIMITS.get_limits(tier, db)
            
            viewed_count = db.query(JobApplication).filter(
                JobApplication.job_id == job_id,
                JobApplication.is_viewed == True
            ).count()
            
            if viewed_count >= limits["resume_access_limit"]:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"You have reached your resume access limit of {limits['resume_access_limit']} candidates for this job under the {limits['name']} plan. Please upgrade your plan."
                )
        app.is_viewed = True
        db.commit()
        db.refresh(app)
        trigger_view_notification = True

    candidate = db.query(Candidate).options(
        joinedload(Candidate.user),
        joinedload(Candidate.taxonomy_domain)
    ).filter(Candidate.id == candidate_id).first()

    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found."
        )

    if trigger_view_notification:
        from app.tasks.notifications import create_in_app_notification_task, get_candidate_action_url
        company = db.query(Company).filter(Company.id == company_id).first()
        comp_name = company.name if company else "Employer"
        create_in_app_notification_task.delay(
            user_id=str(candidate.user_id),
            title="Resume Viewed!",
            content=f"Your profile has been viewed by '{comp_name}' for the job '{job.title}'.",
            notification_type="resume_view",
            action_url=get_candidate_action_url(app.status)
        )

    # Resolve the resume used (direct link or fallback)
    resume = None
    if app.resume_id:
        resume = db.query(Resume).options(
            joinedload(Resume.sections)
        ).filter(
            Resume.id == app.resume_id,
            Resume.is_deleted == False
        ).first()

    if not resume:
        resume = db.query(Resume).options(
            joinedload(Resume.sections)
        ).filter(
            Resume.candidate_id == candidate_id,
            Resume.job_id == job_id,
            Resume.is_deleted == False
        ).order_by(Resume.is_ai_optimized.desc(), Resume.updated_at.desc()).first()
        
    if not resume:
        resume = db.query(Resume).options(
            joinedload(Resume.sections)
        ).filter(
            Resume.candidate_id == candidate_id,
            Resume.is_primary == True,
            Resume.is_deleted == False
        ).first()

    # Calculate AI match score
    ai_score = 0
    if resume and resume.overall_embedding is not None and job:
        try:
            matching_service = MatchingEngine(db)
            score_details = matching_service.score_resume_object_for_job_object(resume, job)
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
    # Statuses: applied, under_review, shortlisted, interviewing, interviewed, offered, hired, rejected
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
        if app_status == "rejected":
            ref_status = (app.rejected_from or "applied").lower()
            if ref_status in completed_statuses:
                return "completed"
            return "pending"
        if app_status in completed_statuses:
            return "completed"
        if app_status in active_statuses:
            return "active"
        return "pending"

    # Helper to get stage updated_at timestamp
    def get_stage_updated_at(completed_statuses: list, current_statuses: list) -> Optional[datetime]:
        if app_status in current_statuses:
            return app.updated_at
            
        if app_status in completed_statuses:
            return app.created_at
            
        if app_status == "rejected":
            ref_status = (app.rejected_from or "applied").lower()
            if ref_status in completed_statuses:
                return app.created_at
        return None

    # 2. Candidate Shortlisted!
    shortlist_completed = ["shortlisted", "interviewing", "interviewed", "offered", "hired"]
    shortlist_current = ["shortlisted"]
    shortlist_active = ["applied", "under_review"]
    timeline.append(
        TimelineEvent(
            title="Candidate Shortlisted!",
            status=get_stage_status(shortlist_completed, shortlist_active),
            updated_at=get_stage_updated_at(shortlist_completed, shortlist_current)
        )
    )

    # 3. Interviewed
    interview_completed = ["interviewing", "interviewed", "offered", "hired"]
    interview_current = ["interviewing", "interviewed"]
    interview_active = []
    timeline.append(
        TimelineEvent(
            title="Interviewed",
            status=get_stage_status(interview_completed, interview_active),
            updated_at=get_stage_updated_at(interview_completed, interview_current)
        )
    )

    # 4. Application successful (Candidate Selected!)
    success_completed = ["offered", "hired"]
    success_current = ["offered", "hired"]
    success_active = ["interviewed"]
    timeline.append(
        TimelineEvent(
            title="Application successful",
            status=get_stage_status(success_completed, success_active),
            updated_at=get_stage_updated_at(success_completed, success_current)
        )
    )

    # If the application is rejected or onhold, we can customize the timeline or keep the flow clear.
    if app_status == "rejected":
        timeline.append(
            TimelineEvent(
                title="Application Rejected",
                status="completed",
                updated_at=app.rejected_at or app.updated_at
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

    # Resolve cover letter format
    cover_letter_url = None
    cover_letter_text = None
    if app.cover_letter:
        if app.cover_letter.strip().startswith(("http://", "https://", "s3://")):
            cover_letter_url = s3_service.get_presigned_url(app.cover_letter)
        else:
            cover_letter_text = app.cover_letter

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
        cover_letter=cover_letter_url or cover_letter_text,
        cover_letter_url=cover_letter_url,
        cover_letter_text=cover_letter_text,
        timeline=timeline,
        is_viewed=app.is_viewed,
        rejected_from=app.rejected_from,
        rejected_at=app.rejected_at
    )


def _get_application_status_label(status: str) -> str:
    mapping = {
        "applied": "Applied",
        "under_review": "Under Review",
        "shortlisted": "Shortlisted",
        "interviewing": "Interviewing",
        "interviewed": "Interviewed",
        "onhold": "On Hold",
        "offered": "Offer Received",
        "hired": "Hired",
        "rejected": "Rejected"
    }
    return mapping.get(status.lower(), status.title())


@router.post("/jobs/{job_id}/close", response_model=EmployerJobDetailResponse)
def employer_close_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> EmployerJobDetailResponse:
    """
    Manually close a job posting.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # Verify job posting exists and belongs to employer's company
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.company_id == company_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    job.status = JobStatus.CLOSED
    db.commit()
    db.refresh(job)

    return get_employer_job_detail(job_id=job_id, db=db, current_user=current_user)


@router.put("/jobs/{job_id}/applicants/{candidate_id}/status", response_model=JobApplicationStatusUpdateResponse)
def update_applicant_status(
    job_id: UUID,
    candidate_id: UUID,
    body: JobApplicationStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> JobApplicationStatusUpdateResponse:
    """
    Update the application status of a candidate for a specific job posting.
    If the status is set to "hired", and the total hired count matches or exceeds the
    job's required number of positions, the job posting is automatically closed.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # Verify job posting exists and belongs to employer's company
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.company_id == company_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    # Verify the application exists
    app = db.query(JobApplication).filter(
        JobApplication.job_id == job_id,
        JobApplication.candidate_id == candidate_id
    ).first()

    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application for this candidate on this job was not found."
        )

    # Normalize and validate the requested status
    requested_status = body.status.strip().lower()
    valid_statuses = {
        "applied", "under_review", "shortlisted", "interviewing",
        "interviewed", "offered", "hired", "rejected", "onhold"
    }
    if requested_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{body.status}'. Must be one of: {', '.join(sorted(valid_statuses))}"
        )

    # Update candidate's job application status
    if requested_status == "rejected":
        if app.status != "rejected":
            app.rejected_from = app.status
            app.rejected_at = datetime.now(timezone.utc)
    else:
        app.rejected_from = None
        app.rejected_at = None
        app.updated_at = datetime.now(timezone.utc)

    app.status = requested_status
    db.flush()  # Push update to DB so count query is accurate

    job_closed_automatically = False
    if requested_status == "hired":
        # Count total hired candidates for this job
        hired_count = db.query(JobApplication).filter(
            JobApplication.job_id == job_id,
            JobApplication.status == "hired"
        ).count()

        if hired_count >= (job.num_positions or 1):
            job.status = JobStatus.CLOSED
            job_closed_automatically = True

    db.commit()

    # Trigger application status change notifications (Email + In-App to Candidate)
    from app.tasks.notifications import send_email_task, create_in_app_notification_task, get_candidate_action_url
    from app.core.config import settings
    status_label = _get_application_status_label(app.status)
    candidate_user_id = str(app.candidate.user_id)
    candidate_email = app.candidate.user.email
    candidate_name = app.candidate.full_name
    company_name = job.company.name if job.company else "the Employer"
    cand_action_url = get_candidate_action_url(app.status)
    
    # Email
    email_data = {
        "name": candidate_name,
        "job_title": job.title,
        "company_name": company_name,
        "status_label": status_label,
        "application_url": f"{settings.FRONTEND_URL}{cand_action_url}"
    }
    send_email_task.delay(
        to_email=candidate_email,
        template_name_or_id="emails/application_status_change.html",
        template_data=email_data,
        subject=f"Application Update: {job.title}"
    )
    
    # In-App
    create_in_app_notification_task.delay(
        user_id=candidate_user_id,
        title="Application Status Updated",
        content=f"Your application status for '{job.title}' has been updated to '{status_label}'.",
        notification_type="application_status_change",
        action_url=cand_action_url
    )

    return JobApplicationStatusUpdateResponse(
        application_id=app.id,
        candidate_id=app.candidate_id,
        job_id=app.job_id,
        status=app.status,
        status_label=_get_application_status_label(app.status),
        job_closed_automatically=job_closed_automatically
    )


@router.post("/jobs/{job_id}/applicants/bulk-status", response_model=BulkStatusUpdateResponse)
def bulk_update_applicant_status(
    job_id: UUID,
    body: BulkStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
) -> BulkStatusUpdateResponse:
    """
    Bulk update the status of multiple applicants for a specific job posting.
    """
    employer = current_user.employer
    if not employer or not employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer is not associated with any company."
        )
    company_id = employer.company_id

    # Verify job posting exists and belongs to employer's company
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.company_id == company_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    # Normalize and validate requested status (normalize "interview" to "interviewing")
    requested_status = body.status.strip().lower()
    if requested_status == "interview":
        requested_status = "interviewing"

    valid_statuses = {
        "applied", "under_review", "shortlisted", "interviewing",
        "interviewed", "offered", "hired", "rejected", "onhold"
    }
    if requested_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{body.status}'. Must be one of: {', '.join(sorted(valid_statuses))}"
        )

    # Fetch matching applications
    apps = db.query(JobApplication).filter(
        JobApplication.job_id == job_id,
        JobApplication.candidate_id.in_(body.candidate_ids)
    ).all()

    if not apps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching applications found for the specified candidates."
        )

    updated_applicants = []
    job_closed_automatically = False

    # Check how many vacancies are filled
    hired_count = db.query(JobApplication).filter(
        JobApplication.job_id == job_id,
        JobApplication.status == "hired"
    ).count()

    for app in apps:
        if requested_status == "rejected":
            if app.status != "rejected":
                app.rejected_from = app.status
                app.rejected_at = datetime.now(timezone.utc)
        else:
            app.rejected_from = None
            app.rejected_at = None
            app.updated_at = datetime.now(timezone.utc)

        app.status = requested_status
        db.flush()

        # Update hired count and check auto close
        if requested_status == "hired":
            hired_count += 1
            if hired_count >= (job.num_positions or 1):
                job.status = JobStatus.CLOSED
                job_closed_automatically = True

        updated_applicants.append(
            JobApplicationStatusUpdateResponse(
                application_id=app.id,
                candidate_id=app.candidate_id,
                job_id=app.job_id,
                status=app.status,
                status_label=_get_application_status_label(app.status),
                job_closed_automatically=job_closed_automatically
            )
        )

    db.commit()

    # Trigger application status change notifications (Email + In-App to each Candidate)
    from app.tasks.notifications import send_email_task, create_in_app_notification_task, get_candidate_action_url
    from app.core.config import settings
    status_label = _get_application_status_label(requested_status)
    company_name = job.company.name if job.company else "the Employer"
    cand_action_url = get_candidate_action_url(requested_status)
    
    for app in apps:
        candidate_user_id = str(app.candidate.user_id)
        candidate_email = app.candidate.user.email
        candidate_name = app.candidate.full_name
        
        # Email
        email_data = {
            "name": candidate_name,
            "job_title": job.title,
            "company_name": company_name,
            "status_label": status_label,
            "application_url": f"{settings.FRONTEND_URL}{cand_action_url}"
        }
        send_email_task.delay(
            to_email=candidate_email,
            template_name_or_id="emails/application_status_change.html",
            template_data=email_data,
            subject=f"Application Update: {job.title}"
        )
        
        # In-App
        create_in_app_notification_task.delay(
            user_id=candidate_user_id,
            title="Application Status Updated",
            content=f"Your application status for '{job.title}' has been updated to '{status_label}'.",
            notification_type="application_status_change",
            action_url=cand_action_url
        )

    return BulkStatusUpdateResponse(
        updated_count=len(updated_applicants),
        updated_applicants=updated_applicants
    )









