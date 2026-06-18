from pydantic import BaseModel, AnyUrl
from typing import Optional

class CandidateStep1Schema(BaseModel):
    resume_url: str
    resume_name: str

class CandidateStep2Schema(BaseModel):
    work_status_id: int

class CandidateStep3Schema(BaseModel):
    taxonomy_domain_id: int

class CandidateStep4Schema(BaseModel):
    visa_status_id: int
