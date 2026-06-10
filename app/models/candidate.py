from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
import uuid

from app.db.base_class import Base

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    profile_picture = Column(String(500), nullable=True)  # URL to profile image
    
    # Onboarding fields
    onboarding_step = Column(Integer, default=0, nullable=False)
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    work_status_id = Column(Integer, ForeignKey("meta_work_statuses.id", ondelete="SET NULL"), nullable=True)
    taxonomy_domain_id = Column(Integer, ForeignKey("taxonomy_domains.id", ondelete="SET NULL"), nullable=True)
    visa_status_id = Column(Integer, ForeignKey("meta_visa_statuses.id", ondelete="SET NULL"), nullable=True)

    # Subscription and Credit System
    plan_tier = Column(String(20), default="free", nullable=False)  # free, pro, premium
    daily_apply_credits_used = Column(Integer, default=0, nullable=False)
    monthly_ai_credits_used = Column(Integer, default=0, nullable=False)
    resume_optimizations_used_this_month = Column(Integer, default=0, nullable=False)
    cover_letters_generated_this_month = Column(Integer, default=0, nullable=False)
    last_credits_reset_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    monthly_credits_reset_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="candidate")
    work_status = relationship("MetaWorkStatus")
    taxonomy_domain = relationship("TaxonomyDomain")
    visa_status = relationship("MetaVisaStatus")
    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    applications = relationship("JobApplication", back_populates="candidate", cascade="all, delete-orphan")
    saved_jobs = relationship("SavedJob", back_populates="candidate", cascade="all, delete-orphan")

    @validates("taxonomy_domain_id", "work_status_id", "visa_status_id")
    def validate_dropdown_fks(self, key, value):
        """Convert 0 or empty values to None to prevent ForeignKey constraints errors"""
        if value in (0, "0", ""):
            return None
        return value

    def __repr__(self):
        return f"<Candidate(id={self.id}, full_name={self.full_name})>"
