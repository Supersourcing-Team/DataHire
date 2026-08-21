from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
import asyncio
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
    
    from app.models.resume import Resume
    from app.services.s3_service import clean_s3_url
    clean_url = clean_s3_url(str(data.resume_url))
    
    # Check if this resume was already parsed during the upload stage
    existing_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.file_url == clean_url
    ).first()
    
    if existing_resume:
        db.query(Resume).filter(Resume.candidate_id == candidate.id).update({Resume.is_primary: False})
        existing_resume.is_primary = True
        if data.resume_name and existing_resume.file_name != data.resume_name:
            existing_resume.file_name = data.resume_name
        db.add(existing_resume)
        
        if existing_resume.taxonomy_domain_id:
            candidate.taxonomy_domain_id = existing_resume.taxonomy_domain_id
    else:
        from app.services.plans_service import PLAN_LIMITS
        tier = candidate.plan_tier or "free"
        limits = PLAN_LIMITS.get_limits(tier, db)
        existing_resumes = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.is_deleted == False
        ).all()
        
        uploaded_resumes_count = sum(1 for r in existing_resumes if not r.is_ai_optimized)
        
        if uploaded_resumes_count >= limits["resume_upload_limits"]:
            raise HTTPException(
                status_code=400,
                detail=f"You have reached your limit of {limits['resume_upload_limits']} uploaded resumes. Please delete an existing resume to complete onboarding."
            )
            
        if len(existing_resumes) >= limits["saved_resumes_limit"]:
            raise HTTPException(
                status_code=400,
                detail=f"You have reached your limit of {limits['saved_resumes_limit']} saved resumes. Please delete an existing resume to complete onboarding."
            )
        from app.services.resume_parser import resume_parser_service
        new_resume = await asyncio.to_thread(
            resume_parser_service.parse_and_save_resume,
            db,
            candidate,
            clean_url,
            data.resume_name,
            True
        )
        
    candidate.onboarding_step = 1
    db.add(candidate)
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
    
    from app.tasks.notifications import send_welcome_notification_task
    send_welcome_notification_task.delay(str(current_user.id))
    
    return {"message": "Candidate onboarding completed successfully"}


@router.post("/company/step1")
async def employer_step_1(
    data: EmployerStep1Schema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    employer = get_employer(current_user, db)
    
    company = None
    if employer.company_id:
        company = db.query(Company).filter(Company.id == employer.company_id).first()
        
    if not company:
        company = Company(name="")
        db.add(company)
        db.commit()
        db.refresh(company)
        employer.company_id = company.id
        db.commit()
        
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

from typing import List

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
    
    # Filter out 0 which represents "Other"
    valid_ids = [domain_id for domain_id in data.taxonomy_domain_ids if domain_id != 0]
    
    from app.models.taxonomy import TaxonomyDomain
    if valid_ids:
        domains = db.query(TaxonomyDomain).filter(TaxonomyDomain.id.in_(valid_ids)).all()
        company.hiring_domains = domains
    else:
        company.hiring_domains = []
        
    company.custom_roles_hiring_for = data.custom_roles
    
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
        
    # Attempt to fetch logo if website is provided and logo_url is not set
    if data.website and not company.logo_url:
        import httpx
        from urllib.parse import urlparse
        from app.services.s3_service import S3Service, S3Folder
        import asyncio
        
        # Extract domain from website url
        parsed_uri = urlparse(str(data.website))
        domain = parsed_uri.netloc or parsed_uri.path
        if domain.startswith("www."):
            domain = domain[4:]
            
        if domain:
            try:
                # Use a small timeout so we don't block onboarding
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(f"https://logos.hunter.io/{domain}")
                    if response.status_code == 200 and response.content:
                        s3_service = S3Service()
                        logo_url = await s3_service.upload_bytes(
                            contents=response.content,
                            filename=f"{domain}.png",
                            folder=S3Folder.COMPANY_LOGO,
                            content_type=response.headers.get("Content-Type", "image/png")
                        )
                        company.logo_url = logo_url
            except Exception as e:
                # Log the error but continue onboarding silently
                print(f"Failed to fetch or upload logo for {domain}: {e}")

    company.onboarding_step = 4
    company.onboarding_completed = True
    db.commit()
    
    from app.tasks.notifications import send_welcome_notification_task
    send_welcome_notification_task.delay(str(current_user.id))
    
    return {"message": "Company onboarding completed successfully"}
