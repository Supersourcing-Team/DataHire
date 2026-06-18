from pydantic import BaseModel
from app.services.s3_service import S3Folder

class FileDeleteRequest(BaseModel):
    url: str
    folder: S3Folder
