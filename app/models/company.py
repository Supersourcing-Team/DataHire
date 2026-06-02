from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
import uuid

from app.db.base_class import Base

company_taxonomy_domains = Table(
    "company_taxonomy_domains",
    Base.metadata,
    Column("company_id", UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
    Column("taxonomy_domain_id", Integer, ForeignKey("taxonomy_domains.id", ondelete="CASCADE"), primary_key=True)
)

class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    website = Column(String(500), nullable=True)
    logo_url = Column(String(500), nullable=True)
    founded_year = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    zipcode = Column(String(20), nullable=True)

    # Contact fields
    office_landline_number = Column(String(20), nullable=True)
    alternate_email = Column(String(255), nullable=True)
    work_mobile_number = Column(String(20), nullable=True)

    # Onboarding fields
    onboarding_step = Column(Integer, default=0, nullable=False)
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    organization_type_id = Column(Integer, ForeignKey("meta_organization_types.id", ondelete="SET NULL"), nullable=True)

    # Many-to-Many Relationship with Taxonomy Domains (Step 3)
    hiring_domains = relationship("TaxonomyDomain", secondary=company_taxonomy_domains)

    # Foreign Keys to Meta Tables
    industry_id = Column(Integer, ForeignKey("meta_industries.id", ondelete="SET NULL"), nullable=True)
    size_id = Column(Integer, ForeignKey("meta_company_sizes.id", ondelete="SET NULL"), nullable=True)
    country_id = Column(Integer, ForeignKey("meta_countries.id", ondelete="SET NULL"), nullable=True)
    state_id = Column(Integer, ForeignKey("meta_states.id", ondelete="SET NULL"), nullable=True)
    city_id = Column(Integer, ForeignKey("meta_cities.id", ondelete="SET NULL"), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    industry = relationship("MetaIndustry")
    size = relationship("MetaCompanySize")
    country = relationship("MetaCountry")
    state = relationship("MetaState")
    city = relationship("MetaCity")
    organization_type = relationship("MetaOrganizationType")

    employers = relationship("Employer", back_populates="company")

    @validates("organization_type_id", "industry_id", "size_id", "country_id", "state_id", "city_id")
    def validate_dropdown_fks(self, key, value):
        """Convert 0 or empty values to None to prevent ForeignKey constraints errors"""
        if value in (0, "0", ""):
            return None
        return value

    def __repr__(self):
        return f"<Company(id={self.id}, name={self.name})>"
