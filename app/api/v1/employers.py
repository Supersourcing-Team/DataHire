from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import require_employer
from app.models.user import User
from app.models.employer import Employer
from app.models.company import Company
from app.schemas.employer import EmployerProfileResponse, CompanyProfileResponse, EmployerProfileUpdate

router = APIRouter(prefix="/employers", tags=["employers"])

def get_employer(current_user: User, db: Session) -> Employer:
    employer = db.query(Employer).filter(Employer.user_id == current_user.id).first()
    if not employer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer profile not found."
        )
    return employer

def _map_employer_to_response(employer: Employer, user: User) -> EmployerProfileResponse:
    company_res = None
    if employer.company:
        c = employer.company
        company_res = CompanyProfileResponse(
            id=c.id,
            name=c.name,
            website=c.website,
            logo_url=c.logo_url,
            founded_year=c.founded_year,
            description=c.description,
            zipcode=c.zipcode,
            office_landline_number=c.office_landline_number,
            alternate_email=c.alternate_email,
            work_mobile_number=c.work_mobile_number,
            onboarding_step=c.onboarding_step,
            onboarding_completed=c.onboarding_completed,
            organization_type_id=c.organization_type_id,
            industry_id=c.industry_id,
            size_id=c.size_id,
            country_id=c.country_id,
            state_id=c.state_id,
            city_id=c.city_id,
            custom_roles_hiring_for=c.custom_roles_hiring_for
        )
    return EmployerProfileResponse(
        id=employer.id,
        user_id=employer.user_id,
        email=user.email,
        contact_person=employer.contact_person,
        phone=employer.phone,
        company=company_res
    )

@router.get("/profile", response_model=EmployerProfileResponse)
def get_employer_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Get the profile details of the authenticated employer.
    """
    employer = get_employer(current_user, db)
    return _map_employer_to_response(employer, current_user)

@router.put("/profile", response_model=EmployerProfileResponse)
def update_employer_profile(
    profile_data: EmployerProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employer),
):
    """
    Update the profile details of the authenticated employer.
    """
    employer = get_employer(current_user, db)
    
    # Update Employer fields if set
    if profile_data.contact_person is not None:
        employer.contact_person = profile_data.contact_person
    if profile_data.phone is not None:
        employer.phone = profile_data.phone
        
    db.add(employer)
    
    # Update or Create associated Company if any company fields are provided
    company_fields = [
        "company_name", "company_website", "company_logo_url", "company_founded_year",
        "company_description", "company_zipcode", "company_office_landline",
        "company_alternate_email", "company_work_mobile", "company_organization_type_id",
        "company_industry_id", "company_size_id", "company_country_id",
        "company_state_id", "company_city_id", "company_custom_roles"
    ]
    
    # Check if any company fields are sent in the request
    dump = profile_data.model_dump(exclude_unset=True)
    has_company_update = any(f in dump for f in company_fields)
    
    if has_company_update:
        company = None
        if employer.company_id:
            company = db.query(Company).filter(Company.id == employer.company_id).first()
            
        if not company:
            # Create new company record if they didn't have one associated
            company = Company(name=profile_data.company_name or "")
            db.add(company)
            db.flush()  # Generate ID
            employer.company_id = company.id
            db.add(employer)
            
        # Map update fields to company fields
        if profile_data.company_name is not None:
            company.name = profile_data.company_name
        if profile_data.company_website is not None:
            company.website = str(profile_data.company_website)
        if profile_data.company_logo_url is not None:
            company.logo_url = profile_data.company_logo_url
        if profile_data.company_founded_year is not None:
            company.founded_year = profile_data.company_founded_year
        if profile_data.company_description is not None:
            company.description = profile_data.company_description
        if profile_data.company_zipcode is not None:
            company.zipcode = profile_data.company_zipcode
        if profile_data.company_office_landline is not None:
            company.office_landline_number = profile_data.company_office_landline
        if profile_data.company_alternate_email is not None:
            company.alternate_email = profile_data.company_alternate_email
        if profile_data.company_work_mobile is not None:
            company.work_mobile_number = profile_data.company_work_mobile
        if profile_data.company_organization_type_id is not None:
            company.organization_type_id = profile_data.company_organization_type_id
        if profile_data.company_industry_id is not None:
            company.industry_id = profile_data.company_industry_id
        if profile_data.company_size_id is not None:
            company.size_id = profile_data.company_size_id
        if profile_data.company_country_id is not None:
            company.country_id = profile_data.company_country_id
        if profile_data.company_state_id is not None:
            company.state_id = profile_data.company_state_id
        if profile_data.company_city_id is not None:
            company.city_id = profile_data.company_city_id
        if profile_data.company_custom_roles is not None:
            company.custom_roles_hiring_for = profile_data.company_custom_roles
            
        db.add(company)
        
    db.commit()
    db.refresh(employer)
    
    return _map_employer_to_response(employer, current_user)
