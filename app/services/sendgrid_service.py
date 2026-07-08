import os
import logging
import httpx
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Jinja2 environment for email templates
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates"
)
# Ensure templates directory exists
os.makedirs(os.path.join(TEMPLATES_DIR, "emails"), exist_ok=True)

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=True
)

class SendGridService:
    @staticmethod
    async def send_mail_with_template(
        to_email: str,
        template_name_or_id: str,
        template_data: Dict[str, Any],
        subject: str,
        from_email: str = settings.SENDGRID_FROM_EMAIL,
        from_name: str = settings.SENDGRID_FROM_NAME,
    ) -> bool:
        """
        Sends an email using SendGrid's Web API.
        
        Args:
            to_email: Recipient email address.
            template_name_or_id: Local Jinja2 template name (e.g. 'emails/welcome.html')
                                 or SendGrid dynamic template ID (starts with 'd-').
            template_data: Key-value dictionary with template variables.
            subject: Subject line (used as fallback for local HTML templates).
            from_email: Sender email address.
            from_name: Sender name.
            
        Returns:
            bool: True if mail was sent or logged successfully, False otherwise.
        """
        is_dynamic_template = template_name_or_id.startswith("d-")

        # Fallback render of local template for logging or local sending
        html_content = ""
        if not is_dynamic_template:
            try:
                template = jinja_env.get_template(template_name_or_id)
                html_content = template.render(**template_data)
            except Exception as e:
                logger.error(f"Failed to render local email template {template_name_or_id}: {str(e)}")
                return False

        if not settings.SENDGRID_API_KEY:
            logger.warning("----- SENDGRID EMAIL STUB -----")
            logger.warning(f"To: {to_email}")
            logger.warning(f"From: {from_name} <{from_email}>")
            logger.warning(f"Subject: {subject}")
            if is_dynamic_template:
                logger.warning(f"SendGrid Dynamic Template ID: {template_name_or_id}")
                logger.warning(f"Template Data: {template_data}")
            else:
                logger.warning("HTML Content Snippet:")
                logger.warning(html_content[:500] + ("..." if len(html_content) > 500 else ""))
            logger.warning("-------------------------------")
            
            # Save local copy for development preview
            if not is_dynamic_template:
                preview_dir = os.path.join(TEMPLATES_DIR, "previews")
                os.makedirs(preview_dir, exist_ok=True)
                preview_file = os.path.join(preview_dir, f"{to_email.replace('@', '_')}_{os.path.basename(template_name_or_id)}")
                with open(preview_file, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"Saved email preview to {preview_file}")
            
            return True

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }

        if is_dynamic_template:
            payload = {
                "personalizations": [
                    {
                        "to": [{"email": to_email}],
                        "dynamic_template_data": template_data
                    }
                ],
                "from": {
                    "email": from_email,
                    "name": from_name
                },
                "template_id": template_name_or_id
            }
        else:
            payload = {
                "personalizations": [
                    {
                        "to": [{"email": to_email}],
                        "subject": subject
                    }
                ],
                "from": {
                    "email": from_email,
                    "name": from_name
                },
                "content": [
                    {
                        "type": "text/html",
                        "value": html_content
                    }
                ]
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in (200, 201, 202):
                    logger.info(f"Email successfully sent to {to_email} via SendGrid")
                    return True
                else:
                    logger.error(f"SendGrid API failed with status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"HTTP error occurred while calling SendGrid API: {str(e)}")
            return False
