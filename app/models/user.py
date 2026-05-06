from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import String as SQLString
import uuid

from app.db.base_class import Base

# Use String type with choices for role
class UserRole:
    CANDIDATE = "candidate"
    EMPLOYER = "employer" 
    ADMIN = "admin"

class AuthProvider:
    LOCAL = "local"
    GOOGLE = "google"
    LINKEDIN = "linkedin"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for OAuth users
    role = Column(String(20), nullable=False, default=UserRole.CANDIDATE)
    auth_provider = Column(String(20), nullable=False, default=AuthProvider.LOCAL)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    candidate = relationship("Candidate", back_populates="user", uselist=False, cascade="all, delete-orphan")
    employer = relationship("Employer", back_populates="user", uselist=False, cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
