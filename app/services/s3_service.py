import boto3
import uuid
from enum import Enum
from fastapi import UploadFile, HTTPException
from botocore.exceptions import NoCredentialsError, ClientError
from app.core.config import settings

class S3Folder(str, Enum):
    JOB_DESCRIPTION = "job-description-stag"
    PROFILE_IMG = "profile-img-stag"
    RESUME = "resume-stag"
    COMPANY_LOGO = "company-logo-stag"

class S3Service:
    def __init__(self):
        # Initialize the S3 client using credentials from config
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.S3_BUCKET_NAME

    async def upload_file(self, file: UploadFile, folder: S3Folder) -> str:
        """Uploads a file to a specific S3 folder and returns the public URL."""
        if not self.bucket_name:
            raise HTTPException(status_code=500, detail="S3_BUCKET_NAME is not configured")

        try:
            # Create a unique filename
            file_extension = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'bin'
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            
            # The S3 object key includes the folder path
            s3_key = f"{folder.value}/{unique_filename}"
            
            # Read file contents
            contents = await file.read()
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=contents,
                ContentType=file.content_type or 'application/octet-stream'
            )
            
            # Construct the public URL
            s3_url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
            
            return s3_url
            
        except NoCredentialsError:
            raise HTTPException(status_code=500, detail="AWS credentials not available")
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")
        finally:
            # Reset file pointer just in case it's used again
            await file.seek(0)
