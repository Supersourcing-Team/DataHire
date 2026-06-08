from sqlalchemy import Column, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base_class import Base

class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    candidate = relationship("Candidate", back_populates="saved_jobs")
    job = relationship("JobPosting")

    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_candidate_saved_job"),
    )

    def __repr__(self):
        return f"<SavedJob(id={self.id}, candidate_id={self.candidate_id}, job_id={self.job_id})>"
