import boto3
import uuid
import asyncio
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
            
            # Upload to S3 in a separate thread
            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=contents,
                ContentType=file.content_type or 'application/octet-stream'
            )
            
            # Construct the public URL
            s3_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": s3_key,
                },
                ExpiresIn=3600,
            )

            return s3_url
            
        except NoCredentialsError:
            raise HTTPException(status_code=500, detail="AWS credentials not available")
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")
        finally:
            # Reset file pointer just in case it's used again
            await file.seek(0)

    async def upload_bytes(self, contents: bytes, filename: str, folder: S3Folder, content_type: str = "image/png") -> str:
        """Uploads raw bytes to a specific S3 folder and returns the presigned URL."""
        if not self.bucket_name:
            raise HTTPException(status_code=500, detail="S3_BUCKET_NAME is not configured")

        try:
            file_extension = filename.split('.')[-1] if '.' in filename else 'bin'
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            s3_key = f"{folder.value}/{unique_filename}"
            
            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=contents,
                ContentType=content_type
            )
            
            s3_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": s3_key,
                },
                ExpiresIn=3600,
            )
            return s3_url
            
        except NoCredentialsError:
            raise HTTPException(status_code=500, detail="AWS credentials not available")
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"S3 byte upload failed: {str(e)}")

    def extract_key(self, url: str) -> str:
        """Extracts the S3 key from any valid S3 URL for this bucket."""
        from urllib.parse import urlparse, unquote
        
        parsed_url = urlparse(url)
        netloc = parsed_url.netloc
        path = parsed_url.path

        is_valid = False
        s3_key = None

        if netloc.startswith(f"{self.bucket_name}."):
            is_valid = True
            s3_key = path.lstrip('/')
        elif path.startswith(f"/{self.bucket_name}/"):
            is_valid = True
            s3_key = path[len(f"/{self.bucket_name}/"):]

        if not is_valid or not s3_key:
            raise ValueError("Invalid S3 URL or does not match current bucket")

        return unquote(s3_key)

    async def delete_file(self, url: str) -> bool:
        """Deletes a file from S3 given its URL."""
        if not self.bucket_name:
            raise HTTPException(status_code=500, detail="S3_BUCKET_NAME is not configured")
            
        try:
            s3_key = self.extract_key(url)
            
            await asyncio.to_thread(
                self.s3_client.delete_object,
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
            
        except NoCredentialsError:
            raise HTTPException(status_code=500, detail="AWS credentials not available")
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"S3 deletion failed: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to delete file: {str(e)}")

    def get_presigned_url(self, url: str, expires_in: int = 3600) -> str:
        """Generates a presigned URL from a static S3 URL."""
        if not url or not self.bucket_name:
            return url
            
        try:
            s3_key = self.extract_key(url)
            
            presigned_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": s3_key,
                },
                ExpiresIn=expires_in,
            )
            return presigned_url
        except Exception:
            return url
