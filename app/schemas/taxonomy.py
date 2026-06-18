from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class TaxonomyBase(BaseModel):
    is_active: bool = True

class TaxonomyResponseBase(TaxonomyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# 1. Domains
class TaxonomyDomainCreate(TaxonomyBase):
    name: str
    slug: str
    metadata_: Optional[Dict[str, Any]] = None

class TaxonomyDomainUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class TaxonomyDomainResponse(TaxonomyDomainCreate, TaxonomyResponseBase):
    pass

# 2. Job Roles
class TaxonomyJobRoleCreate(TaxonomyBase):
    domain_id: int
    parent_role_id: Optional[int] = None
    name: str
    slug: str
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    required_skills: Optional[List[str]] = None
    optional_skills: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    metadata_: Optional[Dict[str, Any]] = None
    is_verified: bool = False

class TaxonomyJobRoleUpdate(BaseModel):
    domain_id: Optional[int] = None
    parent_role_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    required_skills: Optional[List[str]] = None
    optional_skills: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    metadata_: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

class TaxonomyJobRoleResponse(TaxonomyJobRoleCreate, TaxonomyResponseBase):
    pass

# 3. Skills
class TaxonomySkillCreate(TaxonomyBase):
    domain_id: int
    parent_skill_id: Optional[int] = None
    name: str
    slug: str
    category: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    related_skills: Optional[List[str]] = None
    metadata_: Optional[Dict[str, Any]] = None
    is_verified: bool = False

class TaxonomySkillUpdate(BaseModel):
    domain_id: Optional[int] = None
    parent_skill_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    related_skills: Optional[List[str]] = None
    metadata_: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

class TaxonomySkillResponse(TaxonomySkillCreate, TaxonomyResponseBase):
    pass
