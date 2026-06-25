from sqlalchemy import Column, String, ForeignKey, DateTime, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base_class import Base

class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="applied", nullable=False)  # applied, under_review, interviewing, offered, rejected
    apply_mode = Column(String(50), default="apply", nullable=False)  # apply (manual), auto-apply
    cover_letter = Column(String, nullable=True)  # Store generated cover letter or notes
    is_viewed = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    candidate = relationship("Candidate", back_populates="applications")
    job = relationship("JobPosting")

    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job_application"),
    )

    def __repr__(self):
        return f"<JobApplication(id={self.id}, candidate_id={self.candidate_id}, job_id={self.job_id}, status={self.status})>"
