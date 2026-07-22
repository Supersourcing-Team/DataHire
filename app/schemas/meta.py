from typing import Optional, Any, Dict
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime

class MetaBase(BaseModel):
    is_active: bool = True

class MetaResponseBase(MetaBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# 1. Countries
class MetaCountryCreate(MetaBase):
    name: str
    iso_code: Optional[str] = None
    currency_code: Optional[str] = None

class MetaCountryUpdate(BaseModel):
    name: Optional[str] = None
    iso_code: Optional[str] = None
    currency_code: Optional[str] = None
    is_active: Optional[bool] = None

class MetaCountryResponse(MetaCountryCreate, MetaResponseBase):
    pass

# 2. States
class MetaStateCreate(MetaBase):
    country_id: int
    name: str
    code: Optional[str] = None

class MetaStateUpdate(BaseModel):
    country_id: Optional[int] = None
    name: Optional[str] = None
    code: Optional[str] = None
    is_active: Optional[bool] = None

class MetaStateResponse(MetaStateCreate, MetaResponseBase):
    pass

# 3. Cities
class MetaCityCreate(MetaBase):
    state_id: int
    country_id: int
    name: str

class MetaCityUpdate(BaseModel):
    state_id: Optional[int] = None
    country_id: Optional[int] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaCityResponse(MetaCityCreate, MetaResponseBase):
    pass

# 4. Employment Types
class MetaEmploymentTypeCreate(MetaBase):
    name: str

class MetaEmploymentTypeUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaEmploymentTypeResponse(MetaEmploymentTypeCreate, MetaResponseBase):
    pass

# 5. Work Modes
class MetaWorkModeCreate(MetaBase):
    name: str

class MetaWorkModeUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaWorkModeResponse(MetaWorkModeCreate, MetaResponseBase):
    pass

# 6. Company Sizes
class MetaCompanySizeCreate(MetaBase):
    label: str
    min_employees: int
    max_employees: Optional[int] = None

class MetaCompanySizeUpdate(BaseModel):
    label: Optional[str] = None
    min_employees: Optional[int] = None
    max_employees: Optional[int] = None
    is_active: Optional[bool] = None

class MetaCompanySizeResponse(MetaCompanySizeCreate, MetaResponseBase):
    pass

# 7. Experience Brackets
class MetaExperienceBracketCreate(MetaBase):
    label: str
    min_years: float
    max_years: Optional[float] = None

class MetaExperienceBracketUpdate(BaseModel):
    label: Optional[str] = None
    min_years: Optional[float] = None
    max_years: Optional[float] = None
    is_active: Optional[bool] = None

class MetaExperienceBracketResponse(MetaExperienceBracketCreate, MetaResponseBase):
    pass

# 8. Seniority Levels
class MetaSeniorityLevelCreate(MetaBase):
    name: str

class MetaSeniorityLevelUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaSeniorityLevelResponse(MetaSeniorityLevelCreate, MetaResponseBase):
    pass

# 9. Education Levels
class MetaEducationLevelCreate(MetaBase):
    name: str

class MetaEducationLevelUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaEducationLevelResponse(MetaEducationLevelCreate, MetaResponseBase):
    pass

# 10. Currencies
class MetaCurrencyCreate(MetaBase):
    code: str
    name: str
    symbol: Optional[str] = None

class MetaCurrencyUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    is_active: Optional[bool] = None

class MetaCurrencyResponse(MetaCurrencyCreate, MetaResponseBase):
    pass

# 11. Subscription Plans
class MetaSubscriptionPlanCreate(MetaBase):
    name: str
    price: float
    currency_id: int
    features: Optional[Dict[str, Any]] = None
    role: Optional[str] = None

class MetaSubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    currency_id: Optional[int] = None
    features: Optional[Dict[str, Any]] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class MetaSubscriptionPlanResponse(MetaSubscriptionPlanCreate, MetaResponseBase):
    pass

# 12. Industries
class MetaIndustryCreate(MetaBase):
    name: str

class MetaIndustryUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaIndustryResponse(MetaIndustryCreate, MetaResponseBase):
    pass

# 13. Organization Types
class MetaOrganizationTypeCreate(MetaBase):
    name: str

class MetaOrganizationTypeUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaOrganizationTypeResponse(MetaOrganizationTypeCreate, MetaResponseBase):
    pass

# 14. Work Statuses
class MetaWorkStatusCreate(MetaBase):
    name: str

class MetaWorkStatusUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaWorkStatusResponse(MetaWorkStatusCreate, MetaResponseBase):
    pass

# 15. Visa Statuses
class MetaVisaStatusCreate(MetaBase):
    name: str

class MetaVisaStatusUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class MetaVisaStatusResponse(MetaVisaStatusCreate, MetaResponseBase):
    pass
