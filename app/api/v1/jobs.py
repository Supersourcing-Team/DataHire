from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.job import JobPosting
from app.models.user import User
from app.schemas.job import JobDashboardCardResponse, JobCreate, JobResponse
from app.core.dependencies import require_employer

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    jobs = (
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
        .order_by(JobPosting.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    response = []
    for job in jobs:
        city_name = job.city.name if job.city else None
        state_name = job.state.name if job.state else None
        country_name = job.country.name if job.country else None
        currency_code = job.currency.code if job.currency else None
        currency_symbol = job.currency.symbol if job.currency else None

        response.append(
            JobDashboardCardResponse(
                id=job.id,
                company_id=job.company_id,
                company_name=job.company.name if job.company else None,
                company_logo_url=job.company.logo_url if job.company else None,
                company_verified=None,
                job_title=job.title,
                ai_score=job.ai_score_threshold,
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
                save_action=None,
                apply_action=None,
            )
        )

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

