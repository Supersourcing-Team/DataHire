from sqlalchemy import Column, String, Integer, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship, validates
import uuid
import enum

class SectionType(str, enum.Enum):
    SUMMARY = "Summary"
    EXPERIENCE = "Experience"
    EDUCATION = "Education"
    PROJECTS = "Projects"
    SKILLS = "Skills"
    CERTIFICATIONS = "Certifications"
    OTHER = "Other"

from app.db.base_class import Base

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    
    # File details
    file_url = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    
    # Versioning
    parent_resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True)
    version_number = Column(Integer, default=1, nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    
    # Metadata for quick filtering
    total_experience_years = Column(Integer, default=0, nullable=False)
    taxonomy_domain_id = Column(Integer, ForeignKey("taxonomy_domains.id", ondelete="SET NULL"), nullable=True)
    
    # Structured Data Extracted via LLM
    extracted_skills = Column(JSONB, nullable=True) # Array of candidate's skills
    
    # Semantic Search
    overall_embedding = Column(Vector(384), nullable=True) # Matches all-MiniLM-L6-v2 dimension
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    candidate = relationship("Candidate")
    taxonomy_domain = relationship("TaxonomyDomain")
    job = relationship("JobPosting")
    sections = relationship("ResumeSection", back_populates="resume", cascade="all, delete-orphan")


    @validates("taxonomy_domain_id")
    def validate_dropdown_fks(self, key, value):
        """Convert 0 or empty values to None to prevent ForeignKey constraints errors"""
        if value in (0, "0", ""):
            return None
        return value

    def __repr__(self):
        return f"<Resume(id={self.id}, candidate_id={self.candidate_id}, version={self.version_number})>"


class ResumeSection(Base):
    __tablename__ = "resume_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    
    section_type = Column(String(50), nullable=False) # Maps to SectionType enum
    
    original_content = Column(Text, nullable=False)
    optimized_content = Column(Text, nullable=True) # Populated by LLM suggestions
    
    # Stores missing keywords, lack of experience flags, visa notes, etc. generated during optimization
    optimization_metadata = Column(JSONB, nullable=True) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    resume = relationship("Resume", back_populates="sections")

    def __repr__(self):
        return f"<ResumeSection(id={self.id}, type={self.section_type})>"
