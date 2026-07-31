import re
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator, Field
from datetime import datetime

class TaxonomyBase(BaseModel):
    is_active: bool = True
    model_config = ConfigDict(populate_by_name=True)

class TaxonomyResponseBase(TaxonomyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

def validate_slug_value(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
        raise ValueError(
            "Slug must contain only lowercase alphanumeric characters and hyphens, "
            "and cannot start or end with a hyphen"
        )
    return v

def validate_metadata_value(v: Any) -> Optional[Dict[str, Any]]:
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        v_stripped = v.strip()
        if not v_stripped:
            return None
        try:
            parsed = json.loads(v_stripped)
        except json.JSONDecodeError as e:
            raise ValueError("Invalid JSON format") from e
        if not isinstance(parsed, dict):
            raise ValueError("Metadata must be a JSON object (dictionary)")
        return parsed
    raise ValueError("Metadata must be a valid JSON object or string representation of a JSON object")

# 1. Domains
class TaxonomyDomainCreate(TaxonomyBase):
    name: str
    slug: str
    metadata_: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        return validate_slug_value(v)

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        return validate_metadata_value(v)

class TaxonomyDomainUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata")
    is_active: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        return validate_slug_value(v)

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        return validate_metadata_value(v)

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
    metadata_: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata")
    is_verified: bool = False

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        return validate_slug_value(v)

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        return validate_metadata_value(v)

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
    metadata_: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata")
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        return validate_slug_value(v)

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        return validate_metadata_value(v)

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
    metadata_: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata")
    is_verified: bool = False

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        return validate_slug_value(v)

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        return validate_metadata_value(v)

class TaxonomySkillUpdate(BaseModel):
    domain_id: Optional[int] = None
    parent_skill_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    related_skills: Optional[List[str]] = None
    metadata_: Optional[Dict[str, Any]] = Field(default=None, validation_alias="metadata")
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        return validate_slug_value(v)

    @field_validator("metadata_", mode="before")
    @classmethod
    def validate_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        return validate_metadata_value(v)

class TaxonomySkillResponse(TaxonomySkillCreate, TaxonomyResponseBase):
    pass
