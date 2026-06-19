from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.job import JobPosting
from app.models.user import User, UserRole
from app.models.candidate import Candidate
from app.models.saved_job import SavedJob
from app.models.application import JobApplication
from app.models.resume import Resume
from app.schemas.job import JobDashboardCardResponse, JobCreate, JobResponse
from app.services.s3_service import S3Service
from app.services.matching_engine import MatchingEngine
from app.schemas.job_seeker import JobApplicationResponse, SaveJobRequest
from app.core.dependencies import require_employer, get_optional_current_active_user, require_candidate


router = APIRouter(prefix="/jobs", tags=["jobs"])
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




@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    job_in: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    # 1. Resolve company_id from current_user.employer.company_id
    if not current_user.employer or not current_user.employer.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employer must create or join a company before posting a job."
        )
    
    # 2. Create the JobPosting object
    db_job = JobPosting(
        **job_in.model_dump(),
        company_id=current_user.employer.company_id
    )
    
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    
    return db_job


@router.post("/{job_id}/apply", response_model=JobApplicationResponse)
def apply_to_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    from app.api.v1.job_seeker import apply_to_job as seeker_apply_to_job
    return seeker_apply_to_job(job_id=job_id, db=db, current_user=current_user)


@router.post("/{job_id}/save-unsave")
def save_or_unsave_job(
    job_id: UUID,
    payload: Optional[SaveJobRequest] = None,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    from app.api.v1.job_seeker import save_or_unsave_job as seeker_save_or_unsave_job
    return seeker_save_or_unsave_job(
        job_id=job_id,
        payload=payload,
        status=status,
        db=db,
        current_user=current_user
    )


