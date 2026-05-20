import random
import string
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.otp import OTPToken
from app.services.email_service import EmailService

class OTPService:
    @staticmethod
    def generate_otp_code(length: int = 6) -> str:
        """Generates a random N-digit numeric OTP."""
        return ''.join(random.choices(string.digits, k=length))

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
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)

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
