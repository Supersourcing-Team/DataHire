from pydantic import BaseModel, AnyUrl
from typing import Optional

class EmployerStep1Schema(BaseModel):
    organization_type_id: int

class EmployerStep2Schema(BaseModel):
    size_id: int

class EmployerStep3Schema(BaseModel):
    roles_hiring_for: str

class EmployerStep4Schema(BaseModel):
    name: str
    website: Optional[AnyUrl] = None
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    city_id: Optional[int] = None
    zipcode: Optional[str] = None
    industry_id: Optional[int] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
