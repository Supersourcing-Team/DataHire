from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from app.services.s3_service import S3Service, S3Folder
from app.core.dependencies import get_current_active_user
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["upload"])
s3_service = S3Service()

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    folder: S3Folder = Form(..., description="The S3 folder to store the file in"),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload a file to a specific folder in S3.
    """
    try:
        url = await s3_service.upload_file(file, folder)
        return {
            "message": "File uploaded successfully",
            "url": url,
            "folder": folder.value
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
