from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.orm import validates
from sqlalchemy.sql import func
from datetime import datetime, timezone

from app.db.base_class import Base

class OTPToken(Base):
    __tablename__ = "otp_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)

    @validates('email')
    def validate_email(self, key, address):
        if address:
            return address.lower().strip()
        return address
    otp_code = Column(String(10), nullable=False) # Plaintext for now, can be expanded if hashed
    purpose = Column(String(50), nullable=False) # e.g. ACCOUNT_VERIFICATION, PASSWORD_RESET
    is_used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def is_valid(self):
        # A simple check (to be used after querying)
        return not self.is_used and self.expires_at > datetime.now(timezone.utc)

    def __repr__(self):
        return f"<OTPToken(id={self.id}, email={self.email}, purpose={self.purpose})>"
