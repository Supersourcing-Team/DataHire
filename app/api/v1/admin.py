from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.core.dependencies import require_admin
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.job import JobPosting
from app.models.user import User
from app.schemas.admin import (
    AdminCandidateResponse,
    AdminCompanyResponse,
    AdminJobResponse
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/candidates", response_model=List[AdminCandidateResponse])
def get_all_candidates(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminCandidateResponse]:
    """List all candidates registered in the platform (Admin only)."""
    candidates = (
        db.query(Candidate)
        .options(
            joinedload(Candidate.user),
            joinedload(Candidate.work_status),
            joinedload(Candidate.taxonomy_domain)
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    response = []
    for cand in candidates:
        response.append(
            AdminCandidateResponse(
                id=cand.id,
                user_id=cand.user_id,
                user_email=cand.user.email,
                full_name=cand.full_name,
                phone=cand.phone,
                profile_picture=cand.profile_picture,
                onboarding_step=cand.onboarding_step,
                onboarding_completed=cand.onboarding_completed,
                work_status_id=cand.work_status_id,
                work_status_name=cand.work_status.name if cand.work_status else None,
                taxonomy_domain_id=cand.taxonomy_domain_id,
                taxonomy_domain_name=cand.taxonomy_domain.name if cand.taxonomy_domain else None,
                visa_status_id=cand.visa_status_id,
                created_at=cand.created_at,
                updated_at=cand.updated_at
            )
        )
    return response


@router.get("/companies", response_model=List[AdminCompanyResponse])
def get_all_companies(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminCompanyResponse]:
    """List all companies registered in the platform (Admin only)."""
    companies = (
        db.query(Company)
        .options(
            joinedload(Company.industry),
            joinedload(Company.size),
            joinedload(Company.country),
            joinedload(Company.state),
            joinedload(Company.city),
            joinedload(Company.organization_type)
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    response = []
    for comp in companies:
        response.append(
            AdminCompanyResponse(
                id=comp.id,
                name=comp.name,
                website=comp.website,
                logo_url=comp.logo_url,
                founded_year=comp.founded_year,
                description=comp.description,
                zipcode=comp.zipcode,
                office_landline_number=comp.office_landline_number,
                alternate_email=comp.alternate_email,
                work_mobile_number=comp.work_mobile_number,
                onboarding_step=comp.onboarding_step,
                onboarding_completed=comp.onboarding_completed,
                organization_type_id=comp.organization_type_id,
                organization_type_name=comp.organization_type.name if comp.organization_type else None,
                industry_id=comp.industry_id,
                industry_name=comp.industry.name if comp.industry else None,
                size_id=comp.size_id,
                size_label=comp.size.label if comp.size else None,
                country_id=comp.country_id,
                country_name=comp.country.name if comp.country else None,
                state_id=comp.state_id,
                state_name=comp.state.name if comp.state else None,
                city_id=comp.city_id,
                city_name=comp.city.name if comp.city else None,
                is_active=comp.is_active,
                created_at=comp.created_at,
                updated_at=comp.updated_at
            )
        )
    return response


@router.get("/jobs", response_model=List[AdminJobResponse])
def get_all_jobs(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminJobResponse]:
    """List all jobs (active, inactive, draft) posted in the platform (Admin only)."""
    jobs = (
        db.query(JobPosting)
        .options(
            joinedload(JobPosting.company),
            joinedload(JobPosting.employment_type),
            joinedload(JobPosting.work_mode),
            joinedload(JobPosting.city),
            joinedload(JobPosting.state),
            joinedload(JobPosting.country),
            joinedload(JobPosting.currency)
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

    response = []
    for job in jobs:
        response.append(
            AdminJobResponse(
                id=job.id,
                company_id=job.company_id,
                company_name=job.company.name if job.company else None,
                title=job.title,
                description=job.description,
                employment_type_id=job.employment_type_id,
                employment_type_name=job.employment_type.name if job.employment_type else None,
                work_mode_id=job.work_mode_id,
                work_mode_name=job.work_mode.name if job.work_mode else None,
                city_id=job.city_id,
                city_name=job.city.name if job.city else None,
                state_id=job.state_id,
                state_name=job.state.name if job.state else None,
                country_id=job.country_id,
                country_name=job.country.name if job.country else None,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                currency_id=job.currency_id,
                currency_code=job.currency.code if job.currency else None,
                start_date=job.start_date,
                application_deadline=job.application_deadline,
                min_experience_years=job.min_experience_years,
                max_experience_years=job.max_experience_years,
                requires_visa_sponsorship=job.requires_visa_sponsorship,
                num_positions=job.num_positions,
                status=job.status,
                is_active=job.is_active,
                created_at=job.created_at,
                updated_at=job.updated_at
            )
        )
    return response
