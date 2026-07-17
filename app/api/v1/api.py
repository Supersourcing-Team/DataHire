from fastapi import APIRouter

# Import routers here as they are created
# from app.api.v1.endpoints import employers, jobs, resumes, users
from app.api.v1.auth import router as auth_router
from app.api.v1.linkedin import router as linkedin_router
from app.api.v1.google import router as google_router
from app.api.v1.jobs import router as jobs_router, job_flow_router
api_router = APIRouter()

# Include routers here as they are created
from app.api.v1.employers import router as employers_router
api_router.include_router(employers_router)
# api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
# api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
# api_router.include_router(users.router, prefix="/users", tags=["users"])

# Include auth router
api_router.include_router(auth_router, tags=["authentication"])

# Include LinkedIn OAuth router
api_router.include_router(linkedin_router, tags=["linkedin-auth"])

# Include Google OAuth router
api_router.include_router(google_router, tags=["google-auth"])

# Include Meta router
from app.api.v1.meta import router as meta_router
api_router.include_router(meta_router)

# Include Taxonomy router
from app.api.v1.taxonomy import router as taxonomy_router
api_router.include_router(taxonomy_router)

# Include Onboarding router
from app.api.v1.onboarding import router as onboarding_router
api_router.include_router(onboarding_router)

# Include Upload router
from app.api.v1.upload import router as upload_router
api_router.include_router(upload_router)

# Include Files router
from app.api.v1.files import router as files_router
api_router.include_router(files_router)

# Include Jobs router
api_router.include_router(jobs_router)
api_router.include_router(job_flow_router)

# Include Job Seeker router
from app.api.v1.job_seeker import router as job_seeker_router
api_router.include_router(job_seeker_router)

# Include Admin router
from app.api.v1.admin import router as admin_router
api_router.include_router(admin_router)

# Include Notifications router
from app.api.v1.notifications import router as notifications_router
api_router.include_router(notifications_router)

# Include Billing router
from app.api.v1.billing import router as billing_router
api_router.include_router(billing_router)

@api_router.get("/")
async def api_info():
    """API information endpoint."""
    return {
        "message": "DataHire API v1",
        "version": "1.0.0",
        "endpoints": {
            "auth": "/auth",
            "linkedin": "/auth/linkedin",
            "google": "/auth/google",
            "jobs_dashboard": "/jobs/dashboard",
            "billing_checkout": "/billing/create-checkout-session",
            "billing_portal": "/billing/create-portal-session",
            "billing_status": "/billing/status",
            "admin_hiring_funnel": "/admin/dashboard/hiring-funnel",
            "admin_growth_analytics": "/admin/dashboard/growth-analytics",
            "admin_candidate_dashboard": "/admin/dashboard/candidates",
            "admin_candidates": "/admin/candidates",
            "admin_candidate_details": "/admin/candidates/{candidate_id}",
            "admin_companies": "/admin/companies",
            "admin_company_details": "/admin/companies/{company_id}/details",
            "admin_organization_dashboard": "/admin/dashboard/organizations",
            "admin_jobs": "/admin/jobs",
            "admin_job_analytics_by_domain": "/admin/dashboard/job_analytics/jobs_by_domain",
            "admin_job_analytics_skill_categories": "/admin/dashboard/job_analytics/skill_categories",
            "admin_geographic_analytics": "/admin/dashboard/job_analytics/geographic",
            "admin_job_details": "/admin/jobs/{job_id}",
            "admin_job_dashboard": "/admin/dashboard/jobs",
            "admin_candidate_analytics_by_domain": "/admin/dashboard/candidate_analytics/candidates_by_domain",
            "admin_candidate_experience_levels": "/admin/dashboard/candidate_analytics/experience_levels",
            "admin_candidate_skill_density": "/admin/dashboard/candidate_analytics/skill_density",
            "admin_hiring_and_jobs": "/admin/dashboard/hiring_&_jobs",
            "admin_company_jobs": "/admin/companies/{company_id}/jobs",
            "admin_ai_match_engine": "/admin/dashboard/ai-match-engine",
            "job_seeker_recommended_jobs_resumes": "/job-seeker/recommended-jobs/resumes",
            # Add more endpoints as they are created
        }
    }

