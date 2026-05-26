from fastapi import APIRouter

# Import routers here as they are created
# from app.api.v1.endpoints import employers, jobs, resumes, users
from app.api.v1.auth import router as auth_router
from app.api.v1.linkedin import router as linkedin_router
from app.api.v1.google import router as google_router
api_router = APIRouter()

# Include routers here as they are created
# api_router.include_router(employers.router, prefix="/employers", tags=["employers"])
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
            # Add more endpoints as they are created
        }
    }
