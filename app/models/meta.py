from sqlalchemy import Column, String, Boolean, DateTime, Float, Integer, ForeignKey, DECIMAL
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.base_class import Base

class MetaCountry(Base):
    __tablename__ = "meta_countries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    iso_code = Column(String(10), nullable=True)
    currency_code = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    states = relationship("MetaState", back_populates="country")
    cities = relationship("MetaCity", back_populates="country")


class MetaState(Base):
    __tablename__ = "meta_states"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    country_id = Column(Integer, ForeignKey("meta_countries.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    country = relationship("MetaCountry", back_populates="states")
    cities = relationship("MetaCity", back_populates="state")


class MetaCity(Base):
    __tablename__ = "meta_cities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    state_id = Column(Integer, ForeignKey("meta_states.id", ondelete="CASCADE"), nullable=False)
    country_id = Column(Integer, ForeignKey("meta_countries.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    pincode = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    state = relationship("MetaState", back_populates="cities")
    country = relationship("MetaCountry", back_populates="cities")


class MetaEmploymentType(Base):
    __tablename__ = "meta_employment_types"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaWorkMode(Base):
    __tablename__ = "meta_work_modes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaCompanySize(Base):
    __tablename__ = "meta_company_sizes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    label = Column(String(255), nullable=False)
    min_employees = Column(Integer, nullable=False)
    max_employees = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaExperienceBracket(Base):
    __tablename__ = "meta_experience_brackets"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    label = Column(String(255), nullable=False)
    min_years = Column(Float, nullable=False)
    max_years = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaSeniorityLevel(Base):
    __tablename__ = "meta_seniority_levels"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class MetaOrganizationType(Base):
    __tablename__ = "meta_organization_types"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class MetaEducationLevel(Base):
    __tablename__ = "meta_education_levels"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaCurrency(Base):
    __tablename__ = "meta_currencies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(10), nullable=False, unique=True)
    symbol = Column(String(10), nullable=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaSubscriptionPlan(Base):
    __tablename__ = "meta_subscription_plans"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    currency_id = Column(Integer, ForeignKey("meta_currencies.id", ondelete="RESTRICT"), nullable=False)
    features = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    currency = relationship("MetaCurrency")


class MetaIndustry(Base):
    __tablename__ = "meta_industries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaWorkStatus(Base):
    __tablename__ = "meta_work_statuses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
