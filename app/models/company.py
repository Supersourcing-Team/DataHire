from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base_class import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    website = Column(String(500), nullable=True)
    logo_url = Column(String(500), nullable=True)
    founded_year = Column(Integer, nullable=True)

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

    employers = relationship("Employer", back_populates="company")

    def __repr__(self):
        return f"<Company(id={self.id}, name={self.name})>"
