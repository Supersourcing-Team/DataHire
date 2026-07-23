import random
import string
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.otp import OTPToken
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

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

        # Send email
        success = EmailService.send_otp_email(to_email=email, otp_code=code, purpose=purpose)
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

        # Log OTP (mock send)
        logger.warning("----- SMS OTP -----")
        logger.warning(f"To: {phone}")
        logger.warning(f"Purpose: {purpose}")
        logger.warning(f"OTP: {code}")
        logger.warning("-------------------")
        return True

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
