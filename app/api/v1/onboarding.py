from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User, UserRole
from app.models.candidate import Candidate
from app.models.employer import Employer
from app.models.company import Company
from app.schemas.candidate_onboarding import (
    CandidateStep1Schema, CandidateStep2Schema,
    CandidateStep3Schema, CandidateStep4Schema
)
from app.schemas.employer_onboarding import (
    EmployerStep1Schema, EmployerStep2Schema,
    EmployerStep3Schema, EmployerStep4Schema
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

def get_candidate(current_user: User, db: Session) -> Candidate:
    if current_user.role != UserRole.CANDIDATE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a candidate")
    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate profile not found")
    return candidate

def get_employer(current_user: User, db: Session) -> Employer:
    if current_user.role != UserRole.EMPLOYER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not an employer")
    employer = db.query(Employer).filter(Employer.user_id == current_user.id).first()
    if not employer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employer profile not found")
    return employer

@router.post("/candidate/step1")
async def candidate_step_1(
    data: CandidateStep1Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    candidate = get_candidate(current_user, db)
    candidate.resume_url = str(data.resume_url)
    candidate.onboarding_step = 1
    db.commit()
    return {"message": "Step 1 completed successfully"}

@router.post("/candidate/step2")
async def candidate_step_2(
    data: CandidateStep2Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    candidate = get_candidate(current_user, db)
    candidate.work_status_id = data.work_status_id
    candidate.onboarding_step = 2
    db.commit()
    return {"message": "Step 2 completed successfully"}

@router.post("/candidate/step3")
async def candidate_step_3(
    data: CandidateStep3Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    candidate = get_candidate(current_user, db)
    candidate.taxonomy_domain_id = data.taxonomy_domain_id
    candidate.onboarding_step = 3
    db.commit()
    return {"message": "Step 3 completed successfully"}

@router.post("/candidate/step4")
async def candidate_step_4(
    data: CandidateStep4Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    candidate = get_candidate(current_user, db)
    candidate.visa_status_id = data.visa_status_id
    candidate.onboarding_step = 4
    candidate.onboarding_completed = True
    db.commit()
    return {"message": "Candidate onboarding completed successfully"}


@router.post("/company/step1")
async def employer_step_1(
    data: EmployerStep1Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    employer = get_employer(current_user, db)
    
    if not employer.company_id:
        company = Company(name="Draft Company")
        db.add(company)
        db.commit()
        db.refresh(company)
        employer.company_id = company.id
        db.commit()
    else:
        company = db.query(Company).filter(Company.id == employer.company_id).first()
        
    company.organization_type_id = data.organization_type_id
    company.onboarding_step = 1
    db.commit()
    return {"message": "Step 1 completed successfully"}

@router.post("/company/step2")
async def employer_step_2(
    data: EmployerStep2Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    employer = get_employer(current_user, db)
    if not employer.company_id:
        raise HTTPException(status_code=400, detail="Must complete Step 1 first")
        
    company = db.query(Company).filter(Company.id == employer.company_id).first()
    company.size_id = data.size_id
    company.onboarding_step = 2
    db.commit()
    return {"message": "Step 2 completed successfully"}

@router.post("/company/step3")
async def employer_step_3(
    data: EmployerStep3Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    employer = get_employer(current_user, db)
    if not employer.company_id:
        raise HTTPException(status_code=400, detail="Must complete Step 1 first")
        
    company = db.query(Company).filter(Company.id == employer.company_id).first()
    company.roles_hiring_for = data.roles_hiring_for
    company.onboarding_step = 3
    db.commit()
    return {"message": "Step 3 completed successfully"}

@router.post("/company/step4")
async def employer_step_4(
    data: EmployerStep4Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    employer = get_employer(current_user, db)
    if not employer.company_id:
        raise HTTPException(status_code=400, detail="Must complete Step 1 first")
        
    company = db.query(Company).filter(Company.id == employer.company_id).first()
    company.name = data.name
    if data.website is not None:
        company.website = str(data.website)
    if data.country_id is not None:
        company.country_id = data.country_id
    if data.state_id is not None:
        company.state_id = data.state_id
    if data.city_id is not None:
        company.city_id = data.city_id
    if data.zipcode is not None:
        company.zipcode = data.zipcode
    if data.industry_id is not None:
        company.industry_id = data.industry_id
    if data.founded_year is not None:
        company.founded_year = data.founded_year
    if data.description is not None:
        company.description = data.description
    if data.office_landline_number is not None:
        company.office_landline_number = data.office_landline_number
    if data.alternate_email is not None:
        company.alternate_email = data.alternate_email
    if data.work_mobile_number is not None:
        company.work_mobile_number = data.work_mobile_number
        
    company.onboarding_step = 4
    company.onboarding_completed = True
    db.commit()
    return {"message": "Company onboarding completed successfully"}
