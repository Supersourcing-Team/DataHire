from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.job import JobPosting
from app.schemas.file_schemas import FileDeleteRequest
from app.services.s3_service import S3Service, S3Folder

router = APIRouter(prefix="/files", tags=["files"])
s3_service = S3Service()

@router.delete("/")
async def delete_file(
    request: FileDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    url_str = str(request.url)
    folder = request.folder

    # Verify ownership and update database
    if folder == S3Folder.RESUME:
        candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
        if not candidate or candidate.resume_url != url_str:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this resume or file not found")
        candidate.resume_url = None

    elif folder == S3Folder.PROFILE_IMG:
        if current_user.profile_picture != url_str:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this profile picture")
        current_user.profile_picture = None
        if current_user.candidate and current_user.candidate.profile_picture == url_str:
            current_user.candidate.profile_picture = None

    elif folder == S3Folder.COMPANY_LOGO:
        if not current_user.employer or not current_user.employer.company_id:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this company logo")
        company = db.query(Company).filter(Company.id == current_user.employer.company_id).first()
        if not company or company.logo_url != url_str:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this company logo")
        company.logo_url = None

    elif folder == S3Folder.JOB_DESCRIPTION:
        if not current_user.employer or not current_user.employer.company_id:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this job description")
        # Find the job posting belonging to this company that has this URL
        job = db.query(JobPosting).filter(
            JobPosting.company_id == current_user.employer.company_id,
            JobPosting.job_description_url == url_str
        ).first()
        if not job:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this job description or file not found")
        job.job_description_url = None

    else:
        raise HTTPException(status_code=400, detail="Invalid folder type")

    # Delete from S3
    try:
        await s3_service.delete_file(url_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    db.commit()

    return {"message": "File deleted successfully"}
