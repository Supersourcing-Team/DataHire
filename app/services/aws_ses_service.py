import os
import logging
import boto3
import asyncio
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader
from botocore.exceptions import ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Jinja2 environment for email templates
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates"
)
os.makedirs(os.path.join(TEMPLATES_DIR, "emails"), exist_ok=True)

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=True
)

class AWSSESService:
    @staticmethod
    def _get_ses_client():
        """Creates and returns a boto3 SES client if credentials are provided."""
        aws_access_key = settings.SES_AWS_ACCESS_KEY_ID or settings.AWS_ACCESS_KEY_ID
        aws_secret = settings.SES_AWS_SECRET_ACCESS_KEY or settings.AWS_SECRET_ACCESS_KEY
        aws_region = settings.SES_AWS_REGION or settings.AWS_REGION or "us-east-1"

        if not aws_access_key or not aws_secret:
            return None
        try:
            return boto3.client(
                "ses",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret,
                region_name=aws_region
            )
        except Exception as e:
            logger.error(f"Failed to initialize AWS SES client: {str(e)}")
            return None

    @classmethod
    async def send_mail_with_template(
        cls,
        to_email: str,
        template_name_or_id: str,
        template_data: Dict[str, Any],
        subject: str,
        from_email: str = settings.SES_FROM_EMAIL,
        from_name: str = "DataHire"
    ) -> bool:
        """
        Sends an email using AWS SES, rendering a local Jinja2 template.
        """
        # Render the template locally
        try:
            template = jinja_env.get_template(template_name_or_id)
            html_content = template.render(**template_data)
        except Exception as e:
            logger.error(f"Failed to render local email template {template_name_or_id}: {str(e)}")
            return False

        # If credentials or provider settings are missing, use local development stub
        client = cls._get_ses_client()
        if not client or settings.EMAIL_PROVIDER != "ses":
            logger.warning("----- AWS SES EMAIL STUB -----")
            logger.warning(f"To: {to_email}")
            logger.warning(f"From: {from_name} <{from_email}>")
            logger.warning(f"Subject: {subject}")
            logger.warning("HTML Content Snippet:")
            logger.warning(html_content[:500] + ("..." if len(html_content) > 500 else ""))
            logger.warning("------------------------------")

            # Save local copy for development preview
            preview_dir = os.path.join(TEMPLATES_DIR, "previews")
            os.makedirs(preview_dir, exist_ok=True)
            preview_file = os.path.join(
                preview_dir, 
                f"{to_email.replace('@', '_')}_{os.path.basename(template_name_or_id)}"
            )
            try:
                with open(preview_file, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"Saved email preview to {preview_file}")
            except Exception as fe:
                logger.error(f"Failed to save local preview file: {str(fe)}")
            
            return True

        # Send using thread pool to make it non-blocking
        return await asyncio.to_thread(
            cls._send_ses_email_sync,
            client=client,
            to_email=to_email,
            html_content=html_content,
            subject=subject,
            from_email=from_email,
            from_name=from_name
        )

    @staticmethod
    def _send_ses_email_sync(
        client,
        to_email: str,
        html_content: str,
        subject: str,
        from_email: str,
        from_name: str
    ) -> bool:
        """Synchronous helper that executes the boto3 SES call."""
        source = f"{from_name} <{from_email}>" if from_name else from_email
        
        # Simple plain-text fallback: strip simple html elements or use a placeholder
        text_content = "To view this email, please use an HTML-compatible email client."

        try:
            response = client.send_email(
                Source=source,
                Destination={
                    "ToAddresses": [to_email]
                },
                Message={
                    "Subject": {
                        "Data": subject,
                        "Charset": "UTF-8"
                    },
                    "Body": {
                        "Html": {
                            "Data": html_content,
                            "Charset": "UTF-8"
                        },
                        "Text": {
                            "Data": text_content,
                            "Charset": "UTF-8"
                        }
                    }
                }
            )
            message_id = response.get("MessageId")
            logger.info(f"Email successfully sent to {to_email} via AWS SES (MessageId: {message_id})")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]
            logger.error(f"AWS SES ClientError [{error_code}]: {error_msg} (Recipient: {to_email})")
            return False
        except Exception as e:
            logger.error(f"Unexpected error calling AWS SES API: {str(e)} (Recipient: {to_email})")
            return False
