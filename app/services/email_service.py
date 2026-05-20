import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class EmailService:
    @staticmethod
    def send_otp_email(to_email: str, otp_code: str, purpose: str = "Verification") -> bool:
        """
        Sends an OTP code via email. Returns True if successful, False otherwise.
        Falls back to console logging if SMTP settings are not fully configured.
        """
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            logger.warning("SMTP settings not configured. Simulated Email Delivery:")
            logger.warning(f"--- OTP for {to_email} ---")
            logger.warning(f"Purpose: {purpose}")
            logger.warning(f"Code: {otp_code}")
            logger.warning("-----------------------------")
            return True

        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg["Subject"] = f"Your {purpose} Code - DataHire"

        body = f"""
        Hello,

        Your One-Time Password (OTP) for {purpose} is:
        
        {otp_code}

        This code will expire in 10 minutes.
        If you did not request this code, please ignore this email.

        Best regards,
        DataHire Team
        """
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
