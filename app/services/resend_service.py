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
os.makedirs(os.path.join(TEMPLATES_DIR, "emails"), exist_ok=True)

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=True
)


class ResendService:
    @staticmethod
    async def send_mail_with_template(
        to_email: str,
        template_name_or_id: str,
        template_data: Dict[str, Any],
        subject: str,
        from_email: Optional[str] = None,
        from_name: str = "DataHire",
    ) -> bool:
        """
        Sends an email using Resend's Web API (HTTPS / Port 443).
        """
        try:
            template = jinja_env.get_template(template_name_or_id)
            html_content = template.render(**template_data)
        except Exception as e:
            logger.error(f"Failed to render local email template {template_name_or_id}: {str(e)}")
            return False

        api_key = getattr(settings, "RESEND_API_KEY", None)
        if not api_key:
            logger.warning("RESEND_API_KEY is not set.")
            return False

        sender = from_email or getattr(settings, "RESEND_FROM_EMAIL", None) or "onboarding@resend.dev"
        from_field = f"{from_name} <{sender}>" if from_name and "<" not in sender else sender

        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": from_field,
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in (200, 201):
                    logger.info(f"Email successfully sent to {to_email} via Resend")
                    return True

                # If domain is not verified on Resend, retry with onboarding@resend.dev
                if response.status_code == 403 and "domain is not verified" in response.text:
                    logger.warning(
                        f"Domain not verified on Resend. Retrying with onboarding@resend.dev for {to_email}..."
                    )
                    payload["from"] = f"{from_name} <onboarding@resend.dev>"
                    retry_resp = await client.post(url, headers=headers, json=payload)
                    if retry_resp.status_code in (200, 201):
                        logger.info(f"Email successfully sent to {to_email} via Resend (sandbox)")
                        return True
                    else:
                        logger.error(f"Resend retry failed: {retry_resp.text}")
                        return False

                logger.error(f"Resend API failed with status {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"HTTP error occurred while calling Resend API: {str(e)}")
            return False
