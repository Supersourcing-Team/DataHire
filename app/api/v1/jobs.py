from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.job import JobPosting, JobStatus
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
    PipelineStageSummary, EmployerCompanyDetails, EmployerJobDetailResponse
)
from app.services.s3_service import S3Service
from app.services.matching_engine import MatchingEngine
from app.schemas.job_seeker import JobApplicationResponse, SaveJobRequest
from app.core.dependencies import require_employer, get_optional_current_active_user, require_candidate


router = APIRouter(prefix="/job-posters", tags=["job-posters"])
job_flow_router = APIRouter(tags=["job-posters"])
s3_service = S3Service()


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

    if salary_min is not None and salary_max is not None:
        return f"{currency_prefix}{salary_min} - {currency_prefix}{salary_max}/month"
    if salary_min is not None:
        return f"{currency_prefix}{salary_min}+/month"
    return f"Up to {currency_prefix}{salary_max}/month"


def _build_location_label(city: Optional[str], state: Optional[str], country: Optional[str]) -> Optional[str]:
    parts = [part for part in [city, state, country] if part]
    return ", ".join(parts) if parts else None


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
        )
        .filter(JobPosting.is_active == True)
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
                score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
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




# @router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
# def create_job(
#     job_in: JobCreate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(require_employer),
# ):
#     # 1. Resolve company_id from current_user.employer.company_id
#     if not current_user.employer or not current_user.employer.company_id:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Employer must create or join a company before posting a job."
#         )
    
#     # 2. Create the JobPosting object
#     db_job = JobPosting(
#         **job_in.model_dump(),
#         company_id=current_user.employer.company_id
#     )
    
#     db.add(db_job)
#     db.commit()
#     db.refresh(db_job)
    
#     return db_job


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
    
    deadline_date = None
    if days_deadline is not None:
        deadline_date = datetime.now(timezone.utc) + timedelta(days=days_deadline)

    db_job = JobPosting(
        **job_data,
        application_deadline=deadline_date,
        company_id=current_user.employer.company_id,
        status=JobStatus.DRAFT,
        is_active=False
    )
    
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
    db_job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
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
    total_jobs = db.query(JobPosting).filter(JobPosting.company_id == company_id).count()

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
    # Fetch all hired applications for the company to aggregate in Python (fully DB independent)
    hired_apps = (
        db.query(JobApplication.created_at)
        .join(JobPosting, JobApplication.job_id == JobPosting.id)
        .filter(
            JobPosting.company_id == company_id,
            JobApplication.status.in_(["offered", "hired"])
        )
        .all()
    )

    now = datetime.now(timezone.utc)
    months_list = []
    for i in range(5, -1, -1):
        target_date = now - timedelta(days=i*30)
        months_list.append((target_date.year, target_date.month, target_date.strftime("%b")))

    monthly_success_rate = []

    for year, month_num, month_name in months_list:
        count_in_month = sum(
            1 for (created_at,) in hired_apps
            if created_at.year == year and created_at.month == month_num
        )
        
        monthly_success_rate.append(
            MonthlySuccessRatePoint(
                month=month_name,
                rate=float(count_in_month)
            )
        )

    # 3. Candidates Hired By Domain
    from app.models.taxonomy import TaxonomyDomain
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

    hires_by_domain = [
        HiresByDomainPoint(
            domain=name,
            count=count
        )
        for name, count in domain_query
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
                created_at=app.created_at
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
                created_at=dj.updated_at
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

    query = db.query(JobPosting).filter(JobPosting.company_id == company_id)

    if job_status and job_status.lower() != "all":
        query = query.filter(JobPosting.status == job_status.lower())

    if search:
        query = query.filter(
            or_(
                JobPosting.title.ilike(f"%{search}%"),
                JobPosting.description.ilike(f"%{search}%")
            )
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
        if job.requires_visa_sponsorship:
            visa_sponsorships.extend(["H1B Visa sponsorship", "TN Visa sponsorship", "L-1 Visa sponsorship"])
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
                status=job.status
            )
        )

    return response


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
    if job.requires_visa_sponsorship:
        visa_sponsorships.extend(["H1B Visa sponsorship", "TN Visa sponsorship", "L-1 Visa sponsorship"])
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
        location=company_loc
    )

    return EmployerJobDetailResponse(
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
        new_applicants_count=applied,
        shortlisted_count=shortlisted,
        deadline_label=deadline_str,
        status=job.status,
        pipeline_summary=pipeline_summary,
        job_overview=job.job_overview,
        about_role=job.about_role,
        requirements=job.requirements,
        responsibilities=job.responsibilities,
        benefits=job.benefits,
        company_details=company_details
    )







