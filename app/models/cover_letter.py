from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.db.base_class import Base

class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True)
    
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    candidate = relationship("Candidate")
    job = relationship("JobPosting")

    def __repr__(self):
        return f"<CoverLetter(id={self.id}, title={self.title}, candidate_id={self.candidate_id})>"
