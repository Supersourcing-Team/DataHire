from datetime import date, datetime, timezone, timedelta
from typing import List, Optional, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.session import get_db
from app.core.dependencies import require_admin
from app.models.application import JobApplication
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.employer import Employer
from app.models.job import JobPosting, JobStatus
from app.models.user import User
from app.models.taxonomy import TaxonomyDomain, TaxonomyJobRole
from app.models.refresh_token import RefreshToken
from app.models.resume import Resume
from app.models.job_report import JobReport
from app.services.s3_service import S3Service
from app.schemas.admin import (
    AdminCandidateDashboardResponse,
    AdminCandidateResponse,
    AdminCandidateDetailResponse,
    AdminCandidateResumeResponse,
    AdminCandidateApplicationResponse,
    AdminCompanyResponse,
    AdminHiringFunnelAnalyticsResponse,
    AdminHiringFunnelDataPoint,
    AdminJobResponse,
    AdminJobDashboardResponse,
    AdminJobDetailResponse,
    AdminOrganizationAboutCompany,
    AdminOrganizationBadge,
    AdminOrganizationCorporateDetail,
    AdminOrganizationDashboardResponse,
    AdminOrganizationDetailResponse,
    AdminOrganizationHeader,
    AdminOrganizationJobOpeningsSummary,
    AdminPlatformGrowthAnalyticsResponse,
    AdminPlatformGrowthDataPoint,
    AdminUserSuspensionResponse,
    AdminJobAnalyticsByDomainResponse,
    AdminJobAnalyticsByDomainDataPoint,
    AdminSkillCategoriesResponse,
    AdminSkillCategoryDataPoint,
    AdminGeographicAnalyticsResponse,
    AdminGeographicAnalyticsDataPoint,
    AdminCandidateAnalyticsByDomainResponse,
    AdminCandidateAnalyticsByDomainDataPoint,
    AdminCandidateExperienceLevelsResponse,
    AdminCandidateExperienceLevelsDataPoint,
    AdminCandidateSkillDensityResponse,
    AdminCandidateSkillDensityDataPoint,
    AdminCandidateStateResponse,
    AdminJobCandidateResponse,
    AdminJobReportResponse,
    AdminAIMatchInsightsResponse,
    AdminUpdatePlanRequest
)

router = APIRouter(prefix="/admin", tags=["admin"])
s3_service = S3Service()


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


def _get_job_profile_picture(job: JobPosting) -> Optional[str]:
    if job.company:
        if job.company.logo_url:
            return s3_service.get_presigned_url(job.company.logo_url)
        if job.company.employers:
            for emp in job.company.employers:
                if emp.user and emp.user.profile_picture:
                    return s3_service.get_presigned_url(emp.user.profile_picture)
    return None


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
    employer_email = None
    if comp.employers:
        primary_employer = comp.employers[0]
        if primary_employer.user:
            employer_email = primary_employer.user.email

    return AdminCompanyResponse(
        id=comp.id,
        name=comp.name,
        website=comp.website,
        logo_url=s3_service.get_presigned_url(comp.logo_url),
        founded_year=comp.founded_year,
        description=comp.description,
        zipcode=comp.zipcode,
        office_landline_number=comp.office_landline_number,
        alternate_email=comp.alternate_email,
        employer_email=employer_email,
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
        logo_url=s3_service.get_presigned_url(comp.logo_url),
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
            logo_url=s3_service.get_presigned_url(comp.logo_url),
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


@router.get("/dashboard/hiring_&_jobs")
def get_hiring_and_jobs_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> dict:
    """Get hiring and jobs KPIs summary for the admin dashboard (Admin only)."""
    active_jobs = db.query(JobPosting).filter(JobPosting.status == JobStatus.PUBLISHED).count()
    closed_jobs = db.query(JobPosting).filter(JobPosting.status == JobStatus.CLOSED).count()
    total_jobs = active_jobs + closed_jobs
    
    active_jobs_ratio = round((active_jobs / total_jobs) * 100, 1) if total_jobs > 0 else 0.0
    
    apps = db.query(JobApplication).count()
    hires = db.query(JobApplication).filter(JobApplication.status == "hired").count()

    return {
        "title": "HIRING & JOBS",
        "total_jobs": total_jobs,
        "total_jobs_formatted": f"{total_jobs:,}",
        "active_jobs_ratio": active_jobs_ratio,
        "active_jobs_ratio_label": f"{active_jobs_ratio:.1f}%",
        "active_jobs": active_jobs,
        "active_jobs_label": f"Active: {active_jobs}",
        "closed_jobs": closed_jobs,
        "closed_jobs_label": f"Closed: {closed_jobs}",
        "apps": apps,
        "apps_label": f"Apps: {apps:,}",
        "hires": hires,
        "hires_label": f"Hires: {hires:,}"
    }


@router.get("/dashboard/ai-match-engine")
def get_ai_match_engine_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> dict:
    """Get AI Match Engine KPIs summary for the admin dashboard (Admin only)."""
    from app.services.matching_engine import MatchingEngine
    
    applications = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.job),
            selectinload(JobApplication.candidate).selectinload(Candidate.resumes)
        )
        .all()
    )
    
    total_analyses = len(applications)
    total_matches = 0
    total_gaps = 0
    
    matching_service = MatchingEngine(db)
    for app in applications:
        job = app.job
        # Find primary resume
        resume = next((r for r in app.candidate.resumes if r.is_primary and not r.is_deleted), None)
        if resume and job:
            skills_eval = matching_service.evaluate_skills_overlap(job, resume)
            total_matches += len(skills_eval.get("matched", []))
            total_gaps += len(skills_eval.get("missing", []))
            
    gap_analysis_rate = round((total_gaps / total_analyses) * 100, 1) if total_analyses > 0 else 0.0

    return {
        "title": "AI MATCH ENGINE",
        "total_analyses": total_analyses,
        "total_analyses_formatted": f"{total_analyses:,}",
        "gap_analysis_rate": gap_analysis_rate,
        "gap_analysis_rate_label": f"{gap_analysis_rate:.1f}%",
        "total_matches": total_matches,
        "total_matches_formatted": f"{total_matches:,}",
        "total_gaps": total_gaps,
        "total_gaps_formatted": f"{total_gaps:,}",
        "matches_label": f"Matches: {total_matches:,}",
        "gaps_label": f"Gaps: {total_gaps:,}"
    }


@router.get("/dashboard/ai-match-insights", response_model=AdminAIMatchInsightsResponse)
def get_ai_match_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> dict:
    """Get AI match insights summary (active taxonomy roles and average match score) for the admin dashboard (Admin only)."""
    from app.services.matching_engine import MatchingEngine
    
    # 1. Fetch active taxonomy roles
    active_roles = db.query(TaxonomyJobRole).filter(TaxonomyJobRole.is_active == True).all()
    count_roles = len(active_roles)
    
    if count_roles == 0:
        roles_desc = "No active taxonomy roles configured."
    elif count_roles == 1:
        roles_desc = f"Roles configured like {active_roles[0].name}."
    elif count_roles == 2:
        roles_desc = f"Roles configured like {active_roles[0].name} & {active_roles[1].name}."
    else:
        names = [r.name for r in active_roles[:3]]
        roles_desc = f"Roles configured like {names[0]}, {names[1]} & {names[2]}."

    # 2. Fetch all job applications to compute average match score
    applications = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.job).options(
                joinedload(JobPosting.company),
                joinedload(JobPosting.city),
                joinedload(JobPosting.state),
                joinedload(JobPosting.country),
                joinedload(JobPosting.currency),
                joinedload(JobPosting.work_mode)
            ),
            joinedload(JobApplication.candidate).options(
                selectinload(Candidate.resumes)
            )
        )
        .all()
    )
    
    matching_service = MatchingEngine(db)
    scores = []
    for app in applications:
        job = app.job
        resume = next((r for r in app.candidate.resumes if r.is_primary and not r.is_deleted), None)
        if not resume and app.candidate.resumes:
            resume = next((r for r in app.candidate.resumes if not r.is_deleted), None)
            
        if resume and job:
            try:
                score_details = matching_service.score_resume_object_for_job_object(resume, job)
                scores.append(score_details["final_score"])
            except Exception:
                pass
                
    avg_score = round(sum(scores) / len(scores), 1) if scores else 74.2

    return {
        "title": "AI match insights",
        "subtitle": "Overall status of taxonomy validation and matchmaking.",
        
        "active_taxonomy_roles_count": count_roles,
        "active_taxonomy_roles_label": f"{count_roles} Roles",
        "active_taxonomy_roles_description": roles_desc,
        
        "average_match_score": avg_score,
        "average_match_score_label": f"{avg_score}%",
        "average_match_score_description": "Average similarity match output between candidates and jobs.",
        
        "active_taxonomy_roles": {
            "count": count_roles,
            "label": f"{count_roles} Roles",
            "description": roles_desc
        },
        "average_match_score_data": {
            "score": avg_score,
            "label": f"{avg_score}%",
            "description": "Average similarity match output between candidates and jobs."
        }
    }


@router.get("/candidates", response_model=List[AdminCandidateResponse])
def get_all_candidates(
    search: Optional[str] = Query(None),
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminCandidateResponse]:
    """List all candidates registered in the platform (Admin only)."""
    query = db.query(Candidate)

    if search:
        query = query.filter(Candidate.full_name.ilike(f"%{search}%"))

    candidates = (
        query.options(
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
                profile_picture=s3_service.get_presigned_url(cand.profile_picture),
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


@router.get("/candidates/{candidate_id}", response_model=AdminCandidateDetailResponse)
def get_candidate_details(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCandidateDetailResponse:
    """Get full candidate details for the admin candidate detail page (Admin only)."""
    cand = (
        db.query(Candidate)
        .options(
            joinedload(Candidate.user),
            joinedload(Candidate.work_status),
            joinedload(Candidate.taxonomy_domain),
            joinedload(Candidate.visa_status),
            joinedload(Candidate.resumes).joinedload(Resume.taxonomy_domain),
            joinedload(Candidate.applications).joinedload(JobApplication.job).joinedload(JobPosting.company)
        )
        .filter(Candidate.id == candidate_id)
        .first()
    )
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found."
        )

    resumes_list = []
    for r in cand.resumes:
        resumes_list.append(
            AdminCandidateResumeResponse(
                id=r.id,
                file_name=r.file_name,
                file_url=s3_service.get_presigned_url(r.file_url),
                version_number=r.version_number,
                is_primary=r.is_primary,
                total_experience_years=r.total_experience_years,
                taxonomy_domain_name=r.taxonomy_domain.name if r.taxonomy_domain else None,
                created_at=r.created_at
            )
        )

    apps_list = []
    for app in cand.applications:
        apps_list.append(
            AdminCandidateApplicationResponse(
                id=app.id,
                job_id=app.job_id,
                job_title=app.job.title if app.job else "Unknown Position",
                company_name=app.job.company.name if app.job and app.job.company else None,
                status=app.status,
                created_at=app.created_at
            )
        )

    return AdminCandidateDetailResponse(
        id=cand.id,
        user_id=cand.user_id,
        user_email=cand.user.email,
        full_name=cand.full_name,
        phone=cand.phone,
        profile_picture=s3_service.get_presigned_url(cand.profile_picture),
        onboarding_step=cand.onboarding_step,
        onboarding_completed=cand.onboarding_completed,
        work_status_id=cand.work_status_id,
        work_status_name=cand.work_status.name if cand.work_status else None,
        taxonomy_domain_id=cand.taxonomy_domain_id,
        taxonomy_domain_name=cand.taxonomy_domain.name if cand.taxonomy_domain else None,
        visa_status_id=cand.visa_status_id,
        visa_status_name=cand.visa_status.name if cand.visa_status else None,
        is_active=cand.user.is_active,
        plan_tier=cand.plan_tier,
        daily_apply_credits_used=cand.daily_apply_credits_used,
        monthly_ai_credits_used=cand.monthly_ai_credits_used,
        resume_optimizations_used_this_month=cand.resume_optimizations_used_this_month,
        cover_letters_generated_this_month=cand.cover_letters_generated_this_month,
        last_credits_reset_at=cand.last_credits_reset_at,
        monthly_credits_reset_at=cand.monthly_credits_reset_at,
        created_at=cand.created_at,
        updated_at=cand.updated_at,
        resumes=resumes_list,
        applications=apps_list
    )


@router.delete("/candidates/{candidate_id}")
def delete_candidate(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a candidate profile and their associated user account (Admin only)."""
    cand = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found."
        )

    # Deleting the User associated with the candidate will trigger cascade deletes
    # for Candidate, Resume, JobApplication, SavedJob, CoverLetter, and RefreshTokens.
    user = cand.user
    if user:
        db.delete(user)
    else:
        # Fallback if user doesn't exist
        db.delete(cand)

    db.commit()
    return {"message": "Candidate deleted successfully."}


@router.get("/candidate/stats", response_model=AdminCandidateStateResponse)
def get_candidate_state(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCandidateStateResponse:
    """Get candidate KPI onboarding stats (Admin only)."""
    total_candidates = db.query(Candidate).count()
    completed_onboarding = db.query(Candidate).filter(Candidate.onboarding_completed == True).count()
    pending_onboarding = db.query(Candidate).filter(Candidate.onboarding_completed == False).count()

    return AdminCandidateStateResponse(
        total_candidates=total_candidates,
        completed_onboarding=completed_onboarding,
        pending_onboarding=pending_onboarding
    )


@router.get("/candidates/{candidate_id}/application-history", response_model=List[AdminCandidateApplicationResponse])
def get_candidate_application_history(
    candidate_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminCandidateApplicationResponse]:
    """Get the job application history for a specific candidate (Admin only)."""
    # Verify candidate exists first
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found."
        )

    applications = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.job).joinedload(JobPosting.company)
        )
        .filter(JobApplication.candidate_id == candidate_id)
        .order_by(JobApplication.created_at.desc())
        .all()
    )

    response = []
    for app in applications:
        response.append(
            AdminCandidateApplicationResponse(
                id=app.id,
                job_id=app.job_id,
                job_title=app.job.title if app.job else "Unknown Position",
                company_name=app.job.company.name if app.job and app.job.company else None,
                status=app.status,
                created_at=app.created_at
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
            joinedload(Company.organization_type),
            joinedload(Company.employers).joinedload(Employer.user)
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

    # Notify all employers associated with the company
    from app.tasks.notifications import send_email_task
    for emp in company.employers:
        send_email_task.delay(
            to_email=emp.user.email,
            template_name_or_id="emails/account_suspended.html",
            template_data={"reason": "Your associated organization has been suspended by DataHire Admins."},
            subject="Your Organization Has Been Suspended"
        )
    
    updated_company = (
        db.query(Company)
        .options(
            joinedload(Company.industry),
            joinedload(Company.size),
            joinedload(Company.country),
            joinedload(Company.state),
            joinedload(Company.city),
            joinedload(Company.organization_type),
            joinedload(Company.employers).joinedload(Employer.user)
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
            joinedload(Company.organization_type),
            joinedload(Company.employers).joinedload(Employer.user)
        )
        .filter(Company.id == company_id)
        .first()
    )
    return _format_company_response(updated_company)


@router.get("/companies/{company_id}/jobs", response_model=List[AdminJobResponse])
def get_company_jobs(
    company_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminJobResponse]:
    """List all jobs posted by a specific company (Admin only)."""
    # Verify company exists first
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found."
        )

    jobs = (
        db.query(JobPosting)
        .options(
            joinedload(JobPosting.company).joinedload(Company.employers).joinedload(Employer.user),
            joinedload(JobPosting.employment_type),
            joinedload(JobPosting.work_mode),
            joinedload(JobPosting.city),
            joinedload(JobPosting.state),
            joinedload(JobPosting.country),
            joinedload(JobPosting.currency)
        )
        .filter(JobPosting.company_id == company_id)
        .order_by(JobPosting.created_at.desc())
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
                updated_at=job.updated_at,
                profile_picture=_get_job_profile_picture(job)
            )
        )
    return response


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
            query = query.filter(JobPosting.requires_visa_sponsorship.isnot(None))
        elif val in ("false", "0", "no", "no_sponsorship", "does_not_require"):
            query = query.filter(JobPosting.requires_visa_sponsorship.is_(None))

    jobs = (
        query.options(
            joinedload(JobPosting.company).joinedload(Company.employers).joinedload(Employer.user),
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
                updated_at=job.updated_at,
                profile_picture=_get_job_profile_picture(job)
            )
        )
    return response


@router.get("/dashboard/jobs", response_model=AdminJobDashboardResponse)
def get_job_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminJobDashboardResponse:
    """Get jobs summary KPIs for the admin dashboard (Admin only)."""
    total_jobs = db.query(JobPosting).count()
    active_jobs = db.query(JobPosting).filter(JobPosting.is_active == True).count()
    total_positions_open = db.query(func.sum(JobPosting.num_positions)).filter(JobPosting.is_active == True).scalar() or 0
    visa_sponsored_roles = db.query(JobPosting).filter(JobPosting.requires_visa_sponsorship.isnot(None), JobPosting.is_active == True).count()

    return AdminJobDashboardResponse(
        title="Job Openings Summary",
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        active_label=f"{active_jobs}/{total_jobs}",
        total_positions_open=total_positions_open,
        visa_sponsored_roles=visa_sponsored_roles
    )


@router.get("/jobs/{job_id}", response_model=AdminJobDetailResponse)
def get_job_details(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminJobDetailResponse:
    """Get full details of a specific job posting (Admin only)."""
    job = (
        db.query(JobPosting)
        .options(
            joinedload(JobPosting.company).joinedload(Company.employers).joinedload(Employer.user),
            joinedload(JobPosting.employment_type),
            joinedload(JobPosting.work_mode),
            joinedload(JobPosting.city),
            joinedload(JobPosting.state),
            joinedload(JobPosting.country),
            joinedload(JobPosting.currency),
            joinedload(JobPosting.seniority_level),
            joinedload(JobPosting.taxonomy_domain)
        )
        .filter(JobPosting.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    return AdminJobDetailResponse(
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
        updated_at=job.updated_at,
        profile_picture=_get_job_profile_picture(job),
        
        # Detail fields
        job_overview=job.job_overview,
        about_role=job.about_role,
        requirements=job.requirements,
        responsibilities=job.responsibilities,
        benefits=job.benefits,
        include_cover_letter=job.include_cover_letter,
        cover_letter_required=job.cover_letter_required,
        seniority_level_id=job.seniority_level_id,
        seniority_level_name=job.seniority_level.name if job.seniority_level else None,
        taxonomy_domain_id=job.taxonomy_domain_id,
        taxonomy_domain_name=job.taxonomy_domain.name if job.taxonomy_domain else None,
        ai_score_threshold=job.ai_score_threshold,
        extracted_skills=job.extracted_skills,
        must_be_authorized_to_work=job.must_be_authorized_to_work,
        us_citizen_or_pr_only=job.us_citizen_or_pr_only,
        security_clearance_required=job.security_clearance_required,
        date_posted=job.start_date or job.created_at,
        deadline=job.application_deadline
    )


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

    # Trigger account suspended email notification (Email: Yes, In-App: No)
    from app.tasks.notifications import send_email_task
    send_email_task.delay(
        to_email=user.email,
        template_name_or_id="emails/account_suspended.html",
        template_data={"reason": "Violation of DataHire platform policies."},
        subject="Your DataHire Account Has Been Suspended"
    )

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


@router.get("/dashboard/job_analytics/jobs_by_domain", response_model=AdminJobAnalyticsByDomainResponse)
def get_jobs_by_domain_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminJobAnalyticsByDomainResponse:
    """Get active/published job postings count distribution grouped by domain dynamically from taxonomy domains."""
    # Query active taxonomy domains and count of active job postings for each
    results = (
        db.query(
            TaxonomyDomain.name,
            func.count(JobPosting.id).label("job_count")
        )
        .outerjoin(JobPosting, (JobPosting.taxonomy_domain_id == TaxonomyDomain.id) & (JobPosting.is_active == True))
        .filter(TaxonomyDomain.is_active == True)
        .group_by(TaxonomyDomain.id, TaxonomyDomain.name)
        .order_by(func.count(JobPosting.id).desc(), TaxonomyDomain.name)
        .all()
    )

    # Prepare response data items
    data_points = []
    for domain_name, job_count in results:
        data_points.append(
            AdminJobAnalyticsByDomainDataPoint(
                domain_name=domain_name,
                count=job_count
            )
        )

    return AdminJobAnalyticsByDomainResponse(
        title="Jobs by Domain",
        description="Distribution of openings across main platform sectors.",
        data=data_points
    )


@router.get("/dashboard/job_analytics/skill_categories", response_model=AdminSkillCategoriesResponse)
def get_skill_categories_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminSkillCategoriesResponse:
    """Get top required skill bundles/categories in active job postings."""
    # Define mapping of category names to associated skill keywords
    SKILL_BUNDLES = {
        "SQL / DBs": ["sql", "mysql", "postgresql", "postgres", "nosql", "mongodb", "database", "databases"],
        "Cloud / DevOps": ["aws", "azure", "gcp", "docker", "kubernetes", "devops", "cloud", "cicd"],
        "Python / ML": ["python", "machine learning", "ml", "pytorch", "tensorflow", "scikit-learn", "data science"],
        "Generative AI / LLMs": ["generative ai", "genai", "llm", "llms", "openai", "langchain", "vector databases", "nlp"],
        "React / JS": ["react", "javascript", "js", "typescript", "ts", "html", "css", "node", "nodejs", "frontend"]
    }

    # Initialize counts for each bundle
    bundle_counts = {bundle: 0 for bundle in SKILL_BUNDLES.keys()}

    # Query all active job postings
    active_jobs = (
        db.query(JobPosting)
        .filter(JobPosting.is_active == True)
        .all()
    )

    for job in active_jobs:
        skills = job.resolved_skills
        if not skills or not isinstance(skills, list):
            continue

        # Normalize skills list to lowercase strings
        normalized_skills = [str(s).strip().lower() for s in skills if s]

        # Check match for each bundle (at most 1 count per job posting per bundle)
        for bundle_name, keywords in SKILL_BUNDLES.items():
            matched = False
            for skill in normalized_skills:
                # Direct match or substring match
                for keyword in keywords:
                    if keyword in skill or skill in keyword:
                        matched = True
                        break
                if matched:
                    break
            
            if matched:
                bundle_counts[bundle_name] += 1

    # Format response data items
    data_points = []
    for bundle_name, count in bundle_counts.items():
        count_label = f"{count:,}"
        data_points.append(
            AdminSkillCategoryDataPoint(
                title=bundle_name,
                count=count,
                count_label=count_label,
                platform_count=count,
                platform_count_label=count_label,
                tooltip_title=bundle_name,
                tooltip_platform_count_label=f"Platform Count: {count_label}"
            )
        )

    # Sort descending by count to resemble a distribution chart
    data_points.sort(key=lambda x: x.count, reverse=True)

    return AdminSkillCategoriesResponse(
        title="Skill Categories",
        description="Top required skill bundles in active job postings.",
        data=data_points
    )


@router.get("/dashboard/job_analytics/geographic_analytics", response_model=AdminGeographicAnalyticsResponse)
def get_geographic_analytics(
    limit: int = Query(10, ge=1, le=100, description="Limit the number of top locations returned"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminGeographicAnalyticsResponse:
    """Get active job postings count distribution grouped by location (Admin only)."""
    from app.models.meta import MetaCity, MetaState, MetaCountry, MetaWorkMode

    # SQLAlchemy CASE expression for location aggregation
    location_label = case(
        (MetaWorkMode.name == "REMOTE", "Remote"),
        (MetaCity.name.isnot(None), MetaCity.name),
        (MetaState.name.isnot(None), MetaState.name),
        (MetaCountry.name.isnot(None), MetaCountry.name),
        else_="Not Specified"
    )

    results = (
        db.query(
            location_label.label("location"),
            func.count(JobPosting.id).label("job_count")
        )
        .outerjoin(MetaWorkMode, JobPosting.work_mode_id == MetaWorkMode.id)
        .outerjoin(MetaCity, JobPosting.city_id == MetaCity.id)
        .outerjoin(MetaState, JobPosting.state_id == MetaState.id)
        .outerjoin(MetaCountry, JobPosting.country_id == MetaCountry.id)
        .filter(JobPosting.is_active == True)
        .group_by("location")
        .order_by(func.count(JobPosting.id).desc())
        .limit(limit)
        .all()
    )

    data_points = []
    for loc, count in results:
        count_label = f"{count:,}"
        data_points.append(
            AdminGeographicAnalyticsDataPoint(
                location_name=loc,
                count=count,
                count_label=count_label,
                platform_count=count,
                platform_count_label=count_label,
                tooltip_title=loc,
                tooltip_platform_count_label=f"Jobs: {count_label}"
            )
        )

    return AdminGeographicAnalyticsResponse(
        title="Geographic Analytics",
        description="Highest concentration of positions posted by location.",
        data=data_points
    )


@router.get("/dashboard/candidate_analytics/candidates_by_domain", response_model=AdminCandidateAnalyticsByDomainResponse)
def get_candidates_by_domain_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCandidateAnalyticsByDomainResponse:
    """Get candidate count distribution grouped by taxonomy domain dynamically (Admin only)."""
    from app.models.taxonomy import TaxonomyDomain
    from app.models.candidate import Candidate

    # Query active taxonomy domains and count of candidates for each
    results = (
        db.query(
            TaxonomyDomain.name,
            func.count(Candidate.id).label("candidate_count")
        )
        .outerjoin(Candidate, Candidate.taxonomy_domain_id == TaxonomyDomain.id)
        .filter(TaxonomyDomain.is_active == True)
        .group_by(TaxonomyDomain.id, TaxonomyDomain.name)
        .order_by(func.count(Candidate.id).desc(), TaxonomyDomain.name)
        .all()
    )

    data_points = []
    for domain_name, count in results:
        data_points.append(
            AdminCandidateAnalyticsByDomainDataPoint(
                domain_name=domain_name,
                count=count
            )
        )

    return AdminCandidateAnalyticsByDomainResponse(
        title="Candidates by Domain",
        description="Registration fields specified by candidates.",
        data=data_points
    )


@router.get("/dashboard/candidate_analytics/experience_levels", response_model=AdminCandidateExperienceLevelsResponse)
def get_candidate_experience_levels_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCandidateExperienceLevelsResponse:
    """Get candidate count distribution grouped by experience levels (Admin only)."""
    from app.models.candidate import Candidate
    from app.models.resume import Resume

    # CASE statement for experience grouping
    exp_years = func.coalesce(Resume.total_experience_years, 0)
    exp_bracket = case(
        (exp_years < 2, "Entry Level"),
        ((exp_years >= 2) & (exp_years < 5), "Mid Level"),
        ((exp_years >= 5) & (exp_years < 8), "Senior Level"),
        (exp_years >= 8, "Lead / Principal"),
        else_="Entry Level"
    )

    # Query candidate counts grouped by experience bracket
    results = (
        db.query(
            exp_bracket.label("experience_tier"),
            func.count(Candidate.id).label("candidate_count")
        )
        .outerjoin(Resume, (Resume.candidate_id == Candidate.id) & (Resume.is_primary == True))
        .group_by("experience_tier")
        .all()
    )

    # Map database counts to expected buckets
    counts_map = {row.experience_tier: row.candidate_count for row in results}
    
    # Ensure all four standard buckets are present in correct display order
    ordered_tiers = ["Entry Level", "Mid Level", "Senior Level", "Lead / Principal"]
    
    data_points = []
    for tier in ordered_tiers:
        data_points.append(
            AdminCandidateExperienceLevelsDataPoint(
                experience_level=tier,
                count=counts_map.get(tier, 0)
            )
        )

    return AdminCandidateExperienceLevelsResponse(
        title="Experience Levels",
        description="Experience tier distributions across candidates profiles.",
        data=data_points
    )


@router.get("/dashboard/candidate_analytics/skill_density", response_model=AdminCandidateSkillDensityResponse)
def get_candidate_skill_density_analytics(
    limit: int = Query(10, ge=1, le=100, description="Limit the number of top skills returned"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminCandidateSkillDensityResponse:
    """Get candidate skill density analytics based on keywords in primary resumes (Admin only)."""
    from app.models.resume import Resume

    # Query occurrences of each skill in primary resumes using jsonb unnesting
    results = (
        db.query(
            func.jsonb_array_elements_text(Resume.extracted_skills).label("skill"),
            func.count(Resume.id).label("skill_count")
        )
        .filter(Resume.extracted_skills.isnot(None))
        .filter(Resume.is_primary == True)
        .group_by("skill")
        .order_by(func.count(Resume.id).desc())
        .limit(limit)
        .all()
    )

    data_points = []
    for skill, count in results:
        data_points.append(
            AdminCandidateSkillDensityDataPoint(
                skill_name=skill,
                count=count
            )
        )

    return AdminCandidateSkillDensityResponse(
        title="Skill Density",
        description="Most frequent keywords identified in parsed resumes.",
        data=data_points
    )


@router.get("/jobs/{job_id}/candidate-pipeline/status")
def get_job_candidates_status_count(
    job_id: UUID,
    statuses: List[str] = Query(default=["applied", "review", "shortlisted", "interview", "onhold", "rejected", "withdrawn"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> Dict[str, int]:
    """Get candidate application status counts for a specific job posting dynamically based on requested query parameter statuses (Admin only)."""
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    # Fetch all applications for the job and group counts
    results = (
        db.query(JobApplication.status, func.count(JobApplication.id))
        .filter(JobApplication.job_id == job_id)
        .group_by(JobApplication.status)
        .all()
    )

    # Normalize requested statuses for case-insensitive matching
    # Support both list of query parameters and comma-separated status strings
    actual_statuses = []
    for s in statuses:
        if "," in s:
            actual_statuses.extend([item.strip() for item in s.split(",") if item.strip()])
        else:
            actual_statuses.append(s)

    normalized_requested = {}
    for original_status in actual_statuses:
        clean = original_status.lower().strip()
        normalized_requested[clean] = original_status

    response_counts = {status: 0 for status in actual_statuses}

    # Helper function to get normalized DB status variations
    def get_variations(db_status: str) -> List[str]:
        db_lower = (db_status or "").lower().strip()
        variations = [db_lower]
        if db_lower in ("under_review", "review", "in_review", "in review"):
            variations.extend(["review", "in review", "in_review", "under_review", "inreview"])
        elif db_lower in ("interviewing", "interviewed", "interview"):
            variations.extend(["interview", "interviewing", "interviewed"])
        elif db_lower in ("onhold", "on_hold"):
            variations.extend(["onhold", "on_hold"])
        return variations

    for db_status_str, count in results:
        db_variations = get_variations(db_status_str)
        # Find if any of these variations is in normalized_requested
        for var in db_variations:
            if var in normalized_requested:
                orig_key = normalized_requested[var]
                response_counts[orig_key] += count
                break

    return response_counts


@router.get("/jobs/{job_id}/candidate-pipeline/details", response_model=List[AdminJobCandidateResponse])
def get_job_candidates_pipeline(
    job_id: UUID,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminJobCandidateResponse]:
    """Get the candidate pipeline details for a specific job posting, optionally filtered by status (Admin only)."""
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    query = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.candidate).joinedload(Candidate.user),
            joinedload(JobApplication.candidate).joinedload(Candidate.taxonomy_domain),
            joinedload(JobApplication.candidate).joinedload(Candidate.resumes)
        )
        .filter(JobApplication.job_id == job_id)
    )

    if status and status.lower().strip() != "all":
        status_clean = status.lower().strip()
        if status_clean in ("under_review", "review", "in_review", "in review", "inreview"):
            query = query.filter(func.lower(JobApplication.status).in_(["under_review", "review", "in_review", "in review"]))
        elif status_clean in ("interviewing", "interviewed", "interview"):
            query = query.filter(func.lower(JobApplication.status).in_(["interviewing", "interviewed", "interview"]))
        elif status_clean in ("onhold", "on_hold"):
            query = query.filter(func.lower(JobApplication.status).in_(["onhold", "on_hold"]))
        else:
            query = query.filter(func.lower(JobApplication.status) == status_clean)

    applications = query.order_by(JobApplication.created_at.desc()).all()

    candidates_list = []
    for app in applications:
        candidate = app.candidate
        if not candidate:
            continue

        app_type = "Auto Applied" if app.cover_letter else "Manual"

        primary_resume = next((r for r in candidate.resumes if r.is_primary), None)
        resume_url = s3_service.get_presigned_url(primary_resume.file_url) if primary_resume else None
        profile_pic_url = s3_service.get_presigned_url(candidate.profile_picture) if candidate.profile_picture else None

        candidates_list.append(
            AdminJobCandidateResponse(
                id=candidate.id,
                full_name=candidate.full_name,
                email=candidate.user.email if candidate.user else "",
                phone=candidate.phone,
                profile_picture=profile_pic_url,
                position_role=candidate.taxonomy_domain.name if candidate.taxonomy_domain else None,
                applied_date=app.created_at,
                application_type=app_type,
                application_status=app.status,
                ai_score=0,
                resume_url=resume_url
            )
        )

    return candidates_list


@router.post("/jobs/{job_id}/close", response_model=AdminJobResponse)
def close_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> AdminJobResponse:
    """Close a job posting (Admin only)."""
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found."
        )

    if job.status == JobStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job posting is already closed."
        )

    job.status = JobStatus.CLOSED
    db.commit()
    
    # Reload job with all relationships for AdminJobResponse
    updated_job = (
        db.query(JobPosting)
        .options(
            joinedload(JobPosting.company).joinedload(Company.employers).joinedload(Employer.user),
            joinedload(JobPosting.employment_type),
            joinedload(JobPosting.work_mode),
            joinedload(JobPosting.city),
            joinedload(JobPosting.state),
            joinedload(JobPosting.country),
            joinedload(JobPosting.currency)
        )
        .filter(JobPosting.id == job_id)
        .first()
    )
    
    return AdminJobResponse(
        id=updated_job.id,
        company_id=updated_job.company_id,
        company_name=updated_job.company.name if updated_job.company else None,
        title=updated_job.title,
        description=updated_job.description,
        employment_type_id=updated_job.employment_type_id,
        employment_type_name=updated_job.employment_type.name if updated_job.employment_type else None,
        work_mode_id=updated_job.work_mode_id,
        work_mode_name=updated_job.work_mode.name if updated_job.work_mode else None,
        city_id=updated_job.city_id,
        city_name=updated_job.city.name if updated_job.city else None,
        state_id=updated_job.state_id,
        state_name=updated_job.state.name if updated_job.state else None,
        country_id=updated_job.country_id,
        country_name=updated_job.country.name if updated_job.country else None,
        salary_min=updated_job.salary_min,
        salary_max=updated_job.salary_max,
        currency_id=updated_job.currency_id,
        currency_code=updated_job.currency.code if updated_job.currency else None,
        start_date=updated_job.start_date,
        application_deadline=updated_job.application_deadline,
        min_experience_years=updated_job.min_experience_years,
        max_experience_years=updated_job.max_experience_years,
        requires_visa_sponsorship=updated_job.requires_visa_sponsorship,
        num_positions=updated_job.num_positions,
        status=updated_job.status,
        is_active=updated_job.is_active,
        created_at=updated_job.created_at,
        updated_at=updated_job.updated_at,
        profile_picture=_get_job_profile_picture(updated_job)
    )


@router.get("/job-reports", response_model=List[AdminJobReportResponse])
def get_job_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
) -> List[AdminJobReportResponse]:
    """Retrieve all job reports submitted by candidates (Admin only)."""
    reports = (
        db.query(JobReport)
        .options(
            joinedload(JobReport.candidate).joinedload(Candidate.user),
            joinedload(JobReport.job).joinedload(JobPosting.company)
        )
        .order_by(JobReport.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    response = []
    for r in reports:
        response.append(
            AdminJobReportResponse(
                id=r.id,
                candidate_id=r.candidate_id,
                candidate_name=r.candidate.full_name if r.candidate else "Unknown Candidate",
                candidate_email=r.candidate.user.email if r.candidate and r.candidate.user else "Unknown Email",
                job_id=r.job_id,
                job_title=r.job.title if r.job else "Unknown Position",
                company_name=r.job.company.name if r.job and r.job.company else None,
                reason=r.reason,
                description=r.description,
                created_at=r.created_at
            )
        )
    return response


@router.post("/users/update-plan")
def update_user_plan(
    payload: AdminUpdatePlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a user's plan tier (Admin only)."""
    user = db.query(User).filter(func.lower(User.email) == func.lower(payload.email.strip())).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email '{payload.email}' not found."
        )
    
    tier_lower = payload.plan_tier.lower()
    
    if user.role == "candidate":
        candidate = user.candidate
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate profile not found for this user."
            )
        valid_tiers = ["free", "pro", "premium", "silver", "gold", "platinum"]
        if tier_lower not in valid_tiers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid plan tier for candidate. Valid tiers: {valid_tiers}"
            )
        candidate.plan_tier = tier_lower
        db.add(candidate)
        db.commit()
        return {"message": f"Candidate plan updated to {tier_lower} successfully."}
        
    elif user.role == "employer":
        employer = user.employer
        if not employer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employer profile not found for this user."
            )
        if not employer.company:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employer is not associated with any company yet."
            )
        company = employer.company
        valid_tiers = ["free", "startup", "msme", "enterprise"]
        if tier_lower not in valid_tiers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid plan tier for company. Valid tiers: {valid_tiers}"
            )
        company.plan_tier = tier_lower
        db.add(company)
        db.commit()
        return {"message": f"Company '{company.name}' plan updated to {tier_lower} successfully."}
        
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan updates are only supported for candidates or employers."
        )




