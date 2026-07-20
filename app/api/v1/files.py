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
    from app.services.s3_service import clean_s3_url
    clean_url = clean_s3_url(url_str)

    # Verify ownership and update database
    if folder == S3Folder.RESUME:
        from app.models.resume import Resume
        linked_resume = db.query(Resume).filter(Resume.file_url == clean_url).first()
        if linked_resume:
            if linked_resume.candidate.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this resume")
            db.delete(linked_resume)

    elif folder == S3Folder.PROFILE_IMG:
        linked_user = db.query(User).filter(User.profile_picture == clean_url).first()
        if linked_user:
            if linked_user.id != current_user.id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this profile picture")
            linked_user.profile_picture = None
            
        linked_candidate = db.query(Candidate).filter(Candidate.profile_picture == clean_url).first()
        if linked_candidate:
            if linked_candidate.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this profile picture")
            linked_candidate.profile_picture = None

    elif folder == S3Folder.COMPANY_LOGO:
        linked_company = db.query(Company).filter(Company.logo_url == clean_url).first()
        if linked_company:
            if not current_user.employer or current_user.employer.company_id != linked_company.id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this company logo")
            linked_company.logo_url = None

    elif folder == S3Folder.JOB_DESCRIPTION:
        linked_job = db.query(JobPosting).filter(JobPosting.job_description_url == clean_url).first()
        if linked_job:
            if not current_user.employer or current_user.employer.company_id != linked_job.company_id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this job description")
            linked_job.job_description_url = None

    elif folder == S3Folder.COVER_LETTER:
        from app.models.application import JobApplication
        linked_app = db.query(JobApplication).filter(JobApplication.cover_letter == clean_url).first()
        if linked_app:
            if linked_app.candidate.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Unauthorized to delete this cover letter")
            linked_app.cover_letter = None

    else:
        raise HTTPException(status_code=400, detail="Invalid folder type")

    # Delete from S3
    try:
        await s3_service.delete_file(url_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    db.commit()

    return {"message": "File deleted successfully"}
