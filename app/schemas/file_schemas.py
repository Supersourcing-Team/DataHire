from pydantic import BaseModel, AnyUrl
from app.services.s3_service import S3Folder

class FileDeleteRequest(BaseModel):
    url: AnyUrl
    folder: S3Folder
