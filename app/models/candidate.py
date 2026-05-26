from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
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
    resume_url = Column(String(500), nullable=True)
    work_status_id = Column(Integer, ForeignKey("meta_work_statuses.id", ondelete="SET NULL"), nullable=True)
    taxonomy_domain_id = Column(Integer, ForeignKey("taxonomy_domains.id", ondelete="SET NULL"), nullable=True)
    visa_status_id = Column(Integer, ForeignKey("meta_visa_statuses.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="candidate")
    work_status = relationship("MetaWorkStatus")
    taxonomy_domain = relationship("TaxonomyDomain")

    def __repr__(self):
        return f"<Candidate(id={self.id}, full_name={self.full_name})>"
