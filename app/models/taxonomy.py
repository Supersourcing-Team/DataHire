from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.db.base_class import Base

class TaxonomyDomain(Base):
    __tablename__ = "taxonomy_domains"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    embedding = Column(Vector(1536), nullable=True) # Assuming standard OpenAI text-embedding-ada-002 size or similar
    metadata_ = Column("metadata", JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    roles = relationship("TaxonomyJobRole", back_populates="domain")
    skills = relationship("TaxonomySkill", back_populates="domain")


class TaxonomyJobRole(Base):
    __tablename__ = "taxonomy_job_roles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    domain_id = Column(Integer, ForeignKey("taxonomy_domains.id", ondelete="CASCADE"), nullable=False)
    parent_role_id = Column(Integer, ForeignKey("taxonomy_job_roles.id", ondelete="SET NULL"), nullable=True)
    
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    
    aliases = Column(JSONB, nullable=True) # Simple list of strings e.g., ["ML Engineer", "Machine Learning Engineer"]
    required_skills = Column(JSONB, nullable=True)
    optional_skills = Column(JSONB, nullable=True)
    weights = Column(JSONB, nullable=True)
    
    embedding = Column(Vector(1536), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    domain = relationship("TaxonomyDomain", back_populates="roles")
    parent_role = relationship("TaxonomyJobRole", remote_side=[id])


class TaxonomySkill(Base):
    __tablename__ = "taxonomy_skills"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    domain_id = Column(Integer, ForeignKey("taxonomy_domains.id", ondelete="CASCADE"), nullable=False)
    parent_skill_id = Column(Integer, ForeignKey("taxonomy_skills.id", ondelete="SET NULL"), nullable=True)
    
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    category = Column(String(255), nullable=True) # e.g., 'Soft Skill', 'Hard Skill', 'Framework'
    description = Column(Text, nullable=True)
    
    aliases = Column(JSONB, nullable=True) # e.g., ["ReactJS", "React.js"]
    related_skills = Column(JSONB, nullable=True)
    
    embedding = Column(Vector(1536), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    domain = relationship("TaxonomyDomain", back_populates="skills")
    parent_skill = relationship("TaxonomySkill", remote_side=[id])
