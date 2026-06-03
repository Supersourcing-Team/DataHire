from sqlalchemy import Column, String, Integer, Text, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship, validates
import uuid

from app.db.base_class import Base

class JobPosting(Base):
    __tablename__ = "job_postings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    job_description_url = Column(String(500), nullable=True) # URL to uploaded JD file
    
    # Core Job Details
    employment_type_id = Column(Integer, ForeignKey("meta_employment_types.id", ondelete="SET NULL"), nullable=True)
    seniority_level_id = Column(Integer, ForeignKey("meta_seniority_levels.id", ondelete="SET NULL"), nullable=True)
    work_mode_id = Column(Integer, ForeignKey("meta_work_modes.id", ondelete="SET NULL"), nullable=True)
    
    # Location
    city_id = Column(Integer, ForeignKey("meta_cities.id", ondelete="SET NULL"), nullable=True)
    state_id = Column(Integer, ForeignKey("meta_states.id", ondelete="SET NULL"), nullable=True)
    country_id = Column(Integer, ForeignKey("meta_countries.id", ondelete="SET NULL"), nullable=True)
    
    # Salary & Dates
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    currency_id = Column(Integer, ForeignKey("meta_currencies.id", ondelete="SET NULL"), nullable=True)
    
    start_date = Column(DateTime(timezone=True), nullable=True)
    application_deadline = Column(DateTime(timezone=True), nullable=True)
    
    # Matching Criteria
    min_experience_years = Column(Integer, default=0, nullable=False)
    max_experience_years = Column(Integer, nullable=True)
    taxonomy_domain_id = Column(Integer, ForeignKey("taxonomy_domains.id", ondelete="SET NULL"), nullable=True)
    
    # AI Selection Criteria
    ai_score_threshold = Column(Integer, default=0, nullable=False) # 0 to 100
    
    # Structured Data Extracted via LLM
    extracted_skills = Column(JSONB, nullable=True) # Array of skills required
    
    # Semantic Search
    embedding = Column(Vector(384), nullable=True) # Matches all-MiniLM-L6-v2 dimension
    
    # Work Authorization & Clearances
    must_be_authorized_to_work = Column(Boolean, default=False)
    requires_visa_sponsorship = Column(Boolean, default=False)
    us_citizen_or_pr_only = Column(Boolean, default=False)
    security_clearance_required = Column(Boolean, default=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company")
    taxonomy_domain = relationship("TaxonomyDomain")
    work_mode = relationship("MetaWorkMode")
    employment_type = relationship("MetaEmploymentType")
    seniority_level = relationship("MetaSeniorityLevel")
    city = relationship("MetaCity")
    state = relationship("MetaState")
    country = relationship("MetaCountry")
    currency = relationship("MetaCurrency")

    @validates(
        "employment_type_id", "seniority_level_id", "work_mode_id", 
        "city_id", "state_id", "country_id", "currency_id", "taxonomy_domain_id"
    )
    def validate_dropdown_fks(self, key, value):
        """Convert 0 or empty values to None to prevent ForeignKey constraints errors"""
        if value in (0, "0", ""):
            return None
        return value

    def __repr__(self):
        return f"<JobPosting(id={self.id}, title={self.title})>"
