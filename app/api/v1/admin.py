from datetime import date, datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.core.dependencies import require_admin
from app.models.application import JobApplication
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.employer import Employer
from app.models.job import JobPosting
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.schemas.admin import (
    AdminCandidateDashboardResponse,
    AdminCandidateResponse,
    AdminCompanyResponse,
    AdminHiringFunnelAnalyticsResponse,
    AdminHiringFunnelDataPoint,
    AdminJobResponse,
    AdminOrganizationAboutCompany,
    AdminOrganizationBadge,
    AdminOrganizationCorporateDetail,
    AdminOrganizationDashboardResponse,
    AdminOrganizationDetailResponse,
    AdminOrganizationHeader,
    AdminOrganizationJobOpeningsSummary,
    AdminPlatformGrowthAnalyticsResponse,
    AdminPlatformGrowthDataPoint,
    AdminUserSuspensionResponse
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _normalize_bucket_key(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _get_registration_counts(db: Session, model, trunc_unit: str, start: datetime, end: datetime) -> dict:
    bucket = func.date_trunc(trunc_unit, model.created_at)
    rows = (
        db.query(bucket.label("bucket"), func.count(model.id).label("total"))
        .filter(model.created_at >= start, model.created_at < end)
        .group_by(bucket)
        .all()
    )
    return {_normalize_bucket_key(row.bucket): row.total for row in rows}


def _format_count_label(count: int) -> str:
    return f"{count:,}"


def _format_created_label(created_at: datetime) -> str:
    created_at_utc = (
        created_at.astimezone(timezone.utc)
        if created_at.tzinfo
        else created_at.replace(tzinfo=timezone.utc)
    )
    return f"Created on {created_at_utc.strftime('%b')} {created_at_utc.day}, {created_at_utc.year}"


def _format_display_value(value) -> str:
    return str(value) if value not in (None, "") else "Not Specified"


def _build_company_initials(name: str) -> str:
    words = [word for word in name.replace("-", " ").split() if word]
    if not words:
        return "NA"
    if len(words) == 1:
        return words[0][:2].upper()
    return "".join(word[0] for word in words[:2]).upper()


def _build_company_location_label(comp: Company) -> str:
    parts = [
        comp.city.name if comp.city else None,
        comp.state.name if comp.state else None,
        comp.country.name if comp.country else None
    ]
    location = ", ".join(part for part in parts if part)
    return location or "Not Specified"


def _build_status_badge(is_active: bool) -> AdminOrganizationBadge:
    if is_active:
        return AdminOrganizationBadge(label="Active", variant="success")
    return AdminOrganizationBadge(label="Suspended", variant="danger")


def _build_onboarding_badge(onboarding_step: int, onboarding_completed: bool) -> AdminOrganizationBadge:
    if onboarding_completed:
        return AdminOrganizationBadge(label="Onboarding Complete", variant="success")
    return AdminOrganizationBadge(
        label=f"Onboarding: Step {onboarding_step}",
        variant="warning"
    )


def _get_application_status_count(db: Session, statuses: List[str]) -> int:
    normalized_statuses = [status_value.lower() for status_value in statuses]
    return (
        db.query(JobApplication)
        .filter(func.lower(JobApplication.status).in_(normalized_statuses))
        .count()
    )


def _build_growth_buckets(period: str) -> tuple:
    now = datetime.now(timezone.utc)

    if period == "weekly":
        current_week = datetime.combine(
            (now - timedelta(days=now.weekday())).date(),
            datetime.min.time(),
            tzinfo=timezone.utc
        )
        buckets = [current_week - timedelta(weeks=offset) for offset in range(7, -1, -1)]
        labels = [bucket.strftime("%b %d") for bucket in buckets]
        return "week", buckets, labels, current_week + timedelta(weeks=1)

    if period == "monthly":
        current_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        buckets = [_add_months(current_month, offset) for offset in range(-11, 1)]
        labels = [bucket.strftime("%b") for bucket in buckets]
        return "month", buckets, labels, _add_months(current_month, 1)

    today = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    buckets = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    labels = [bucket.strftime("%a") for bucket in buckets]
    return "day", buckets, labels, today + timedelta(days=1)


def _format_company_response(comp: Company) -> AdminCompanyResponse:
    return AdminCompanyResponse(
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


def _format_organization_detail_response(comp: Company, job_openings_count: int) -> AdminOrganizationDetailResponse:
    organization_type_label = _format_display_value(
        comp.organization_type.name if comp.organization_type else None
    )
    industry_name = comp.industry.name if comp.industry else None
    size_label = comp.size.label if comp.size else None
    country_name = comp.country.name if comp.country else None
    state_name = comp.state.name if comp.state else None
    city_name = comp.city.name if comp.city else None
    location_label = _build_company_location_label(comp)
    status_badge = _build_status_badge(comp.is_active)
    onboarding_badge = _build_onboarding_badge(
        comp.onboarding_step,
        comp.onboarding_completed
    )
    job_count_label = _format_count_label(job_openings_count)
    jobs_endpoint = f"/admin/companies/{comp.id}/jobs"

    corporate_details = [
        AdminOrganizationCorporateDetail(
            key="industry_sector",
            label="Industry Sector",
            value=industry_name,
            value_label=_format_display_value(industry_name)
        ),
        AdminOrganizationCorporateDetail(
            key="website",
            label="Website",
            value=comp.website,
            value_label=_format_display_value(comp.website)
        ),
        AdminOrganizationCorporateDetail(
            key="alternate_contact_email",
            label="Alternate Contact Email",
            value=comp.alternate_email,
            value_label=_format_display_value(comp.alternate_email)
        ),
        AdminOrganizationCorporateDetail(
            key="work_mobile",
            label="Work Mobile",
            value=comp.work_mobile_number,
            value_label=_format_display_value(comp.work_mobile_number)
        ),
        AdminOrganizationCorporateDetail(
            key="office_landline",
            label="Office Landline",
            value=comp.office_landline_number,
            value_label=_format_display_value(comp.office_landline_number)
        ),
        AdminOrganizationCorporateDetail(
            key="company_size",
            label="Company Size",
            value=size_label,
            value_label=_format_display_value(size_label)
        ),
        AdminOrganizationCorporateDetail(
            key="founded_in",
            label="Founded In",
            value=str(comp.founded_year) if comp.founded_year else None,
            value_label=_format_display_value(comp.founded_year)
        ),
        AdminOrganizationCorporateDetail(
            key="location",
            label="Location",
            value=location_label if location_label != "Not Specified" else None,
            value_label=location_label
        ),
    ]

    return AdminOrganizationDetailResponse(
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
        industry_name=industry_name,
        size_id=comp.size_id,
        size_label=size_label,
        country_id=comp.country_id,
        country_name=country_name,
        state_id=comp.state_id,
        state_name=state_name,
        city_id=comp.city_id,
        city_name=city_name,
        location_label=location_label,
        is_active=comp.is_active,
        created_at=comp.created_at,
        updated_at=comp.updated_at,
        header=AdminOrganizationHeader(
            id=comp.id,
            name=comp.name,
            initials=_build_company_initials(comp.name),
            logo_url=comp.logo_url,
            organization_type_id=comp.organization_type_id,
            organization_type_name=comp.organization_type.name if comp.organization_type else None,
            organization_type_label=organization_type_label,
            is_active=comp.is_active,
            status_label=status_badge.label,
            status_badge=status_badge,
            onboarding_step=comp.onboarding_step,
            onboarding_completed=comp.onboarding_completed,
            onboarding_badge=onboarding_badge,
            created_at=comp.created_at,
            created_label=_format_created_label(comp.created_at)
        ),
        corporate_details=corporate_details,
        about_company=AdminOrganizationAboutCompany(
            title="About the Company",
            description=comp.description,
            description_label=comp.description or "No description provided for this organization yet."
        ),
        job_openings_summary=AdminOrganizationJobOpeningsSummary(
            title=f"Job Openings ({job_count_label})",
            count=job_openings_count,
            count_label=job_count_label,
            description="Manage active recruitment listings published by this organization.",
            jobs_endpoint=jobs_endpoint
        )
    )


@router.get("/dashboard/candidates", response_model=AdminCandidateDashboardResponse)
def get_candidate_dashboard_details(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCandidateDashboardResponse:
    """Get candidate summary card details for the admin dashboard."""
    total_candidates = db.query(Candidate).count()
    active_candidates = (
        db.query(Candidate)
        .join(Candidate.user)
        .filter(User.is_active == True)
        .count()
    )
    suspended_candidates = total_candidates - active_candidates
    active_ratio = (
        round((active_candidates / total_candidates) * 100, 1)
        if total_candidates
        else 0.0
    )

    return AdminCandidateDashboardResponse(
        title="CANDIDATES",
        total_candidates=total_candidates,
        active_ratio=active_ratio,
        active_ratio_label=f"{active_ratio:.1f}%",
        active_candidates=active_candidates,
        active_label=f"{active_candidates} Active",
        suspended_candidates=suspended_candidates,
        suspended_label=f"{suspended_candidates} Suspended"
    )


@router.get("/dashboard/organizations", response_model=AdminOrganizationDashboardResponse)
def get_organization_dashboard_details(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminOrganizationDashboardResponse:
    """Get organization summary card details for the admin dashboard."""
    total_organizations = db.query(Company).count()
    active_organizations = (
        db.query(Company)
        .filter(Company.is_active == True)
        .count()
    )
    suspended_organizations = total_organizations - active_organizations
    active_ratio = (
        round((active_organizations / total_organizations) * 100, 1)
        if total_organizations
        else 0.0
    )

    return AdminOrganizationDashboardResponse(
        title="ORGANIZATIONS",
        total_organizations=total_organizations,
        active_ratio=active_ratio,
        active_ratio_label=f"{active_ratio:.1f}%",
        active_organizations=active_organizations,
        active_label=f"{active_organizations} Active",
        suspended_organizations=suspended_organizations,
        suspended_label=f"{suspended_organizations} Suspended"
    )


@router.get("/dashboard/growth-analytics", response_model=AdminPlatformGrowthAnalyticsResponse)
def get_platform_growth_analytics(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminPlatformGrowthAnalyticsResponse:
    """Get candidate and employer registration analytics for the admin dashboard."""
    trunc_unit, buckets, labels, end = _build_growth_buckets(period)
    start = buckets[0]

    candidate_counts = _get_registration_counts(db, Candidate, trunc_unit, start, end)
    employer_counts = _get_registration_counts(db, Employer, trunc_unit, start, end)

    data = []
    for bucket, label in zip(buckets, labels):
        bucket_key = bucket.date()
        data.append(
            AdminPlatformGrowthDataPoint(
                label=label,
                bucket_start=bucket,
                candidates=candidate_counts.get(bucket_key, 0),
                employers=employer_counts.get(bucket_key, 0)
            )
        )

    return AdminPlatformGrowthAnalyticsResponse(
        title="Platform Growth Analytics",
        description="Track the registration pace of Candidates and Employers.",
        period=period,
        candidates_label="Candidates",
        employers_label="Employers",
        data=data
    )


@router.get("/dashboard/hiring-funnel", response_model=AdminHiringFunnelAnalyticsResponse)
def get_hiring_funnel_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminHiringFunnelAnalyticsResponse:
    """Get platform-level hiring funnel analytics for the admin dashboard."""
    stages = [
        ("Organizations", db.query(Company).count()),
        ("Jobs Posted", db.query(JobPosting).count()),
        ("Applications", db.query(JobApplication).count()),
        ("Shortlisted", _get_application_status_count(db, ["under_review", "shortlisted"])),
        ("Interviewed", _get_application_status_count(db, ["interviewing", "interviewed"])),
        ("Hired", _get_application_status_count(db, ["offered", "hired"])),
    ]

    data = []
    for title, count in stages:
        count_label = _format_count_label(count)
        data.append(
            AdminHiringFunnelDataPoint(
                title=title,
                count=count,
                count_label=count_label,
                platform_count=count,
                platform_count_label=count_label,
                tooltip_title=title,
                tooltip_platform_count_label=f"Platform Count: {count_label}"
            )
        )

    return AdminHiringFunnelAnalyticsResponse(
        title="Hiring Funnel Analytics",
        description="Visual drop-off from platform onboarding down to successful hires.",
        data=data
    )


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
    search: Optional[str] = None,
    organization_type_id: Optional[int] = None,
    industry_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminCompanyResponse]:
    """List all companies registered in the platform (Admin only)."""
    query = db.query(Company)

    if search:
        query = query.filter(Company.name.ilike(f"%{search}%"))

    if organization_type_id not in (None, 0):
        query = query.filter(Company.organization_type_id == organization_type_id)

    if industry_id not in (None, 0):
        query = query.filter(Company.industry_id == industry_id)

    companies = (
        query.options(
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
        response.append(_format_company_response(comp))
    return response


@router.get("/companies/{company_id}/details", response_model=AdminOrganizationDetailResponse)
def get_company_details(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminOrganizationDetailResponse:
    """Get full organization details for the admin organization detail page."""
    company = (
        db.query(Company)
        .options(
            joinedload(Company.industry),
            joinedload(Company.size),
            joinedload(Company.country),
            joinedload(Company.state),
            joinedload(Company.city),
            joinedload(Company.organization_type)
        )
        .filter(Company.id == company_id)
        .first()
    )
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found."
        )

    job_openings_count = (
        db.query(JobPosting)
        .filter(JobPosting.company_id == company_id)
        .count()
    )

    return _format_organization_detail_response(company, job_openings_count)


@router.post("/companies/{company_id}/suspend", response_model=AdminCompanyResponse)
def suspend_company(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCompanyResponse:
    """Suspend an organization (Admin only)."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found."
        )
    
    if company.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is already suspended."
        )
        
    company.is_active = False
    
    # Soft delete (deactivate) all job postings created by this organization
    db.query(JobPosting).filter(JobPosting.company_id == company_id).update(
        {"is_active": False}, synchronize_session=False
    )
    
    db.commit()
    
    updated_company = (
        db.query(Company)
        .options(
            joinedload(Company.industry),
            joinedload(Company.size),
            joinedload(Company.country),
            joinedload(Company.state),
            joinedload(Company.city),
            joinedload(Company.organization_type)
        )
        .filter(Company.id == company_id)
        .first()
    )
    return _format_company_response(updated_company)


@router.post("/companies/{company_id}/revoke-suspension", response_model=AdminCompanyResponse)
def revoke_company(
    company_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCompanyResponse:
    """Activate/Revoke suspension of an organization (Admin only)."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found."
        )
    
    if company.is_active is True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is already active."
        )
        
    company.is_active = True
    db.commit()
    
    updated_company = (
        db.query(Company)
        .options(
            joinedload(Company.industry),
            joinedload(Company.size),
            joinedload(Company.country),
            joinedload(Company.state),
            joinedload(Company.city),
            joinedload(Company.organization_type)
        )
        .filter(Company.id == company_id)
        .first()
    )
    return _format_company_response(updated_company)

@router.get("/jobs", response_model=List[AdminJobResponse])
def get_all_jobs(
    search: Optional[str] = None,
    work_mode_id: Optional[int] = None,
    visa: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminJobResponse]:
    """List all jobs (active, inactive, draft) posted in the platform (Admin only)."""
    query = db.query(JobPosting)

    if search:
        from app.models.company import Company
        from app.models.meta import MetaCity, MetaState, MetaCountry

        query = (
            query.join(Company, JobPosting.company_id == Company.id)
            .outerjoin(MetaCity, JobPosting.city_id == MetaCity.id)
            .outerjoin(MetaState, JobPosting.state_id == MetaState.id)
            .outerjoin(MetaCountry, JobPosting.country_id == MetaCountry.id)
            .filter(
                or_(
                    JobPosting.title.ilike(f"%{search}%"),
                    Company.name.ilike(f"%{search}%"),
                    MetaCity.name.ilike(f"%{search}%"),
                    MetaState.name.ilike(f"%{search}%"),
                    MetaCountry.name.ilike(f"%{search}%")
                )
            )
        )

    if work_mode_id not in (None, 0):
        query = query.filter(JobPosting.work_mode_id == work_mode_id)

    if visa is not None:
        val = str(visa).lower().strip()
        if val in ("true", "1", "yes", "sponsorship_required", "requires_visa_sponsorship", "requires_visa"):
            query = query.filter(JobPosting.requires_visa_sponsorship == True)
        elif val in ("false", "0", "no", "no_sponsorship", "does_not_require"):
            query = query.filter(JobPosting.requires_visa_sponsorship == False)

    jobs = (
        query.options(
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


@router.post("/users/{user_id}/suspend", response_model=AdminUserSuspensionResponse)
def suspend_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminUserSuspensionResponse:
    """Suspend a user (soft delete) and invalidate all their active sessions (Admin only)."""
    # Guard against self-suspension
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot suspend themselves"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Suspend user
    user.is_active = False
    
    # Invalidate active refresh tokens
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete()
    
    db.commit()
    db.refresh(user)

    return AdminUserSuspensionResponse(
        message="User suspended successfully",
        user_id=user.id,
        is_active=user.is_active
    )


@router.post("/users/{user_id}/revoke-suspension", response_model=AdminUserSuspensionResponse)
def revoke_user_suspension(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminUserSuspensionResponse:
    """Revoke user suspension (Admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Activate user
    user.is_active = True
    db.commit()
    db.refresh(user)

    return AdminUserSuspensionResponse(
        message="User suspension revoked successfully",
        user_id=user.id,
        is_active=user.is_active
    )
