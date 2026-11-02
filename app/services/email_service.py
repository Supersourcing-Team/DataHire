import os
import logging
import smtplib
import asyncio
from typing import Dict, Any, Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
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


class EmailService:
    @classmethod
    async def send_mail_with_template(
        cls,
        to_email: str,
        template_name_or_id: str,
        template_data: Dict[str, Any],
        subject: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> bool:
        """
        Sends an email using standard SMTP, rendering a local Jinja2 template.
        """
        sender_email = from_email or settings.SMTP_FROM_EMAIL
        sender_name = from_name or getattr(settings, "SMTP_FROM_NAME", "DataHire")

        # Render template
        try:
            template = jinja_env.get_template(template_name_or_id)
            html_content = template.render(**template_data)
        except Exception as e:
            logger.error(f"Failed to render local email template {template_name_or_id}: {str(e)}")
            return False

        # Fallback for development environments if SMTP not configured
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            logger.warning("SMTP settings not configured.")
            logger.warning("----- SMTP EMAIL STUB -----")
            logger.warning(f"To: {to_email}")
            logger.warning(f"From: {sender_name} <{sender_email}>")
            logger.warning(f"Subject: {subject}")
            logger.warning(f"Template: {template_name_or_id}")
            logger.warning("---------------------------")
            return True

        return await asyncio.to_thread(
            cls._send_smtp_sync,
            to_email=to_email,
            html_content=html_content,
            subject=subject,
            from_email=sender_email,
            from_name=sender_name
        )

    @staticmethod
    def _send_smtp_sync(
        to_email: str,
        html_content: str,
        subject: str,
        from_email: str,
        from_name: str
    ) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = formataddr((from_name, from_email))
            msg["To"] = to_email
            msg["Subject"] = subject

            # Plain text fallback
            plain_text = "To view this email, please use an HTML-compatible email client."
            msg.attach(MIMEText(plain_text, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            port = int(settings.SMTP_PORT or 587)
            if port == 465:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=3) as server:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, port, timeout=3) as server:
                    server.starttls()
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)

            logger.info(f"Email successfully sent to {to_email} via SMTP (Subject: {subject})")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email} via SMTP: {str(e)}")
            return False

    @classmethod
    def send_otp_email(
        cls,
        to_email: str,
        otp_code: str,
        purpose: str = "Verification"
    ) -> bool:
        """
        Sends an OTP email synchronously using the Jinja2 template.
        """
        purpose_label = purpose.replace("_", " ").title()
        subject = f"Your {purpose_label} Code - DataHire"
        template_data = {
            "purpose": purpose_label,
            "otp_code": otp_code
        }

        try:
            template = jinja_env.get_template("emails/otp.html")
            html_content = template.render(**template_data)
        except Exception as e:
            logger.error(f"Failed to render OTP template: {str(e)}")
            return False

        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            logger.warning("SMTP settings not configured.")
            logger.warning("----- OTP EMAIL -----")
            logger.warning(f"To: {to_email}")
            logger.warning(f"Purpose: {purpose}")
            logger.warning(f"OTP: {otp_code}")
            logger.warning("---------------------")
            return True

        sender_email = settings.SMTP_FROM_EMAIL
        sender_name = getattr(settings, "SMTP_FROM_NAME", "DataHire")
        return cls._send_smtp_sync(
            to_email=to_email,
            html_content=html_content,
            subject=subject,
            from_email=sender_email,
            from_name=sender_name
        )
