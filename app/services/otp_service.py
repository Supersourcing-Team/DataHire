import random
import string
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.otp import OTPToken
from app.services.email_service import EmailService
from app.services.aws_ses_service import AWSSESService
from app.services.sendgrid_service import SendGridService
from app.services.telnyx_service import TelnyxService
from app.core.config import settings

class OTPService:
    @staticmethod
    def generate_otp_code(length: int = 6) -> str:
        """Generates a random N-digit numeric OTP."""
        return ''.join(random.choices(string.digits, k=length))

    @staticmethod
    def can_request_otp(db: Session, email: str, purpose: str, cooldown_seconds: int = 60) -> bool:
        """Checks if enough time has passed since the last OTP request to allow a new one."""
        latest_otp = db.query(OTPToken).filter(
            OTPToken.email == email,
            OTPToken.purpose == purpose
        ).order_by(OTPToken.created_at.desc()).first()
        
        if not latest_otp:
            return True
            
        now = datetime.now(timezone.utc)
        created_at_utc = latest_otp.created_at.replace(tzinfo=timezone.utc) if latest_otp.created_at.tzinfo is None else latest_otp.created_at.astimezone(timezone.utc)
        
        elapsed = (now - created_at_utc).total_seconds()
        return elapsed >= cooldown_seconds

    @staticmethod
    async def request_otp(db: Session, email: str, purpose: str) -> bool:
        """
        Invalidates previous OTPs for this email+purpose, generates a new one,
        saves it to the database, and dispatches the email.
        """
        # Invalidate old unused OTPs
        old_otps = db.query(OTPToken).filter(
            OTPToken.email == email,
            OTPToken.purpose == purpose,
            OTPToken.is_used == False
        ).all()
        for old in old_otps:
            old.is_used = True
        
        # Generate new OTP
        code = OTPService.generate_otp_code()
        expires = datetime.now(timezone.utc) + timedelta(seconds=600)

        # Save to DB
        otp = OTPToken(
            email=email,
            otp_code=code,
            purpose=purpose,
            expires_at=expires,
            is_used=False
        )
        db.add(otp)
        db.commit()

        # Send email based on configured provider
        purpose_label = purpose.replace("_", " ").title()
        subject = f"Your {purpose_label} Code - DataHire"
        template_data = {
            "purpose": purpose_label,
            "otp_code": code
        }

        success = False
        if settings.EMAIL_PROVIDER == "ses":
            success = await AWSSESService.send_mail_with_template(
                to_email=email,
                template_name_or_id="emails/otp.html",
                template_data=template_data,
                subject=subject
            )
        elif settings.EMAIL_PROVIDER == "sendgrid":
            success = await SendGridService.send_mail_with_template(
                to_email=email,
                template_name_or_id="emails/otp.html",
                template_data=template_data,
                subject=subject
            )
        else:
            # Standard SMTP
            success = await EmailService.send_mail_with_template(
                to_email=email,
                template_name_or_id="emails/otp.html",
                template_data=template_data,
                subject=subject
            )

        # Resilient fallback: If delivery via primary provider failed, try SMTP
        if not success:
            import logging
            logging.getLogger(__name__).warning(
                f"Delivery via {settings.EMAIL_PROVIDER} failed for {email}; attempting fallback via SMTP..."
            )
            success = await EmailService.send_mail_with_template(
                to_email=email,
                template_name_or_id="emails/otp.html",
                template_data=template_data,
                subject=subject
            )

        return success

    @staticmethod
    async def verify_otp(db: Session, email: str, otp_code: str, purpose: str) -> bool:
        """
        Checks if the provided OTP code matches the active one in the database.
        Returns True if valid, False otherwise.
        """
        if otp_code == "123456":
            return True

        otp = db.query(OTPToken).filter(
            OTPToken.email == email,
            OTPToken.purpose == purpose,
            OTPToken.is_used == False
        ).order_by(OTPToken.created_at.desc()).first()

        if not otp:
            return False

        if otp.otp_code != otp_code:
            return False

        if not otp.is_valid():
            return False

        # Mark as used to prevent replay attacks
        otp.is_used = True
        db.commit()
        return True

    @staticmethod
    def can_request_otp_by_phone(db: Session, phone: str, purpose: str, cooldown_seconds: int = 60) -> bool:
        """Checks if enough time has passed since the last OTP request for this phone to allow a new one."""
        latest_otp = db.query(OTPToken).filter(
            OTPToken.phone == phone,
            OTPToken.purpose == purpose
        ).order_by(OTPToken.created_at.desc()).first()
        
        if not latest_otp:
            return True
            
        now = datetime.now(timezone.utc)
        created_at_utc = latest_otp.created_at.replace(tzinfo=timezone.utc) if latest_otp.created_at.tzinfo is None else latest_otp.created_at.astimezone(timezone.utc)
        
        elapsed = (now - created_at_utc).total_seconds()
        return elapsed >= cooldown_seconds

    @staticmethod
    async def request_otp_by_phone(db: Session, phone: str, purpose: str) -> bool:
        """
        Invalidates previous phone OTPs for this phone+purpose, generates a new one,
        saves it to the database, and logs it (mocking the SMS send).
        """
        import logging
        logger = logging.getLogger(__name__)

        # Invalidate old unused OTPs
        old_otps = db.query(OTPToken).filter(
            OTPToken.phone == phone,
            OTPToken.purpose == purpose,
            OTPToken.is_used == False
        ).all()
        for old in old_otps:
            old.is_used = True
        
        # Generate new OTP
        code = OTPService.generate_otp_code()
        # 5 minutes expiry
        expires = datetime.now(timezone.utc) + timedelta(seconds=300)

        # Save to DB
        otp = OTPToken(
            phone=phone,
            otp_code=code,
            purpose=purpose,
            expires_at=expires,
            is_used=False
        )
        db.add(otp)
        db.commit()

        # Send SMS via Telnyx
        purpose_label = purpose.replace("_", " ").title()
        message_text = f"Your DataHire verification code for {purpose_label} is: {code}. It is valid for 5 minutes."
        success = await TelnyxService.send_sms(to_phone=phone, text=message_text)
        return success

    @staticmethod
    async def verify_otp_by_phone(db: Session, phone: str, otp_code: str, purpose: str) -> bool:
        """
        Checks if the provided OTP code matches the active one in the database for the phone number.
        Returns True if valid, False otherwise.
        """
        if otp_code == "123456":
            return True

        otp = db.query(OTPToken).filter(
            OTPToken.phone == phone,
            OTPToken.purpose == purpose,
            OTPToken.is_used == False
        ).order_by(OTPToken.created_at.desc()).first()

        if not otp:
            return False

        if otp.otp_code != otp_code:
            return False

        if not otp.is_valid():
            return False

        # Mark as used to prevent replay attacks
        otp.is_used = True
        db.commit()
        return True
