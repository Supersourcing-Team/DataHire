from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
import asyncio
from app.services.s3_service import S3Service, S3Folder
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/upload", tags=["upload"])
s3_service = S3Service()

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Form(..., description="The S3 folder to store the file in"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload a file to a specific folder in S3. If it's a resume, it is parsed and saved.
    """
    folder_str = folder.strip().lower()
    if folder_str in ("cover-letter", "cover-letters", "cover-letter-stag", "cover_letter", "cover_letters"):
        target_folder = S3Folder.COVER_LETTER
    elif folder_str in ("resume", "resumes", "resume-stag"):
        target_folder = S3Folder.RESUME
    elif folder_str in ("profile-img", "profile-image", "profile-img-stag", "profile_img", "profile_image"):
        target_folder = S3Folder.PROFILE_IMG
    elif folder_str in ("company-logo", "company-logo-stag", "company_logo"):
        target_folder = S3Folder.COMPANY_LOGO
    elif folder_str in ("job-description", "job-description-stag", "job_description"):
        target_folder = S3Folder.JOB_DESCRIPTION
    else:
        try:
            target_folder = S3Folder(folder_str)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid folder type '{folder}'")

    try:
        url = await s3_service.upload_file(file, target_folder)
        
        if target_folder == S3Folder.RESUME:
            if not current_user.candidate:
                raise HTTPException(status_code=400, detail="User is not a candidate and cannot upload a resume.")
            
            # Read bytes directly from UploadFile
            await file.seek(0)
            file_bytes = await file.read()
            
            # Extract text (run in threadpool)
            from app.services.resume_parser import resume_parser_service
            text = await asyncio.to_thread(resume_parser_service.extract_text_from_pdf, file_bytes)
            
            # Get active taxonomy domains
            from app.models.taxonomy import TaxonomyDomain
            domains = db.query(TaxonomyDomain).filter(TaxonomyDomain.is_active == True).all()
            active_domain_names = [d.name for d in domains]
            
            # Parse via Gemini (run in threadpool)
            parse_result = await asyncio.to_thread(resume_parser_service.parse_resume_text, text, active_domain_names)
            
            # Resolve domain
            recommended_domain_name = parse_result.get("recommended_domain")
            domain_id = None
            if recommended_domain_name:
                matched_domain = next((d for d in domains if d.name.lower() == recommended_domain_name.lower()), None)
                if matched_domain:
                    domain_id = matched_domain.id
            
            # Create Resume in db
            from app.models.resume import Resume, ResumeSection, SectionType
            existing_resumes = db.query(Resume).filter(Resume.candidate_id == current_user.candidate.id).all()
            is_primary = len(existing_resumes) == 0
            
            if is_primary:
                db.query(Resume).filter(Resume.candidate_id == current_user.candidate.id).update({Resume.is_primary: False})
            
            total_exp = parse_result.get("total_experience_years", 0)
            skills = parse_result.get("skills", [])
            structured_data = parse_result.get("structured_data")
            
            new_resume = Resume(
                candidate_id=current_user.candidate.id,
                file_url=url,
                file_name=file.filename,
                is_primary=is_primary,
                version_number=len(existing_resumes) + 1,
                total_experience_years=total_exp,
                taxonomy_domain_id=domain_id,
                extracted_skills=skills,
                structured_data=structured_data
            )
            
            # Save sections
            sections_dict = parse_result.get("sections", {}) or {}
            for sec_name, sec_content in sections_dict.items():
                if not sec_content or not sec_content.strip():
                    continue
                    
                matched_sec_type = None
                for st in SectionType:
                    if st.value.lower() == sec_name.lower():
                        matched_sec_type = st
                        break
                
                if not matched_sec_type:
                    matched_sec_type = SectionType.OTHER
                    
                # Decompose section-wise structured data
                sec_structured_content = None
                if structured_data:
                    if matched_sec_type == SectionType.SUMMARY:
                        sec_structured_content = structured_data.get("summary")
                    elif matched_sec_type == SectionType.EXPERIENCE:
                        sec_structured_content = structured_data.get("experience")
                    elif matched_sec_type == SectionType.EDUCATION:
                        sec_structured_content = structured_data.get("education")
                    elif matched_sec_type == SectionType.PROJECTS:
                        sec_structured_content = structured_data.get("projects")
                    elif matched_sec_type == SectionType.SKILLS:
                        sec_structured_content = structured_data.get("skills")
                    elif matched_sec_type == SectionType.CERTIFICATIONS:
                        sec_structured_content = structured_data.get("certifications")
                    elif matched_sec_type == SectionType.OTHER:
                        sec_structured_content = {
                            "achievements": structured_data.get("achievements", []),
                            "languages": structured_data.get("languages", []),
                            "customSections": structured_data.get("customSections", [])
                        }
                    
                new_section = ResumeSection(
                    section_type=matched_sec_type.value,
                    original_content=sec_content,
                    structured_content=sec_structured_content
                )
                new_resume.sections.append(new_section)
                
            db.add(new_resume)
            
            # Update candidate taxonomy domain if primary
            if is_primary and domain_id:
                current_user.candidate.taxonomy_domain_id = domain_id
                db.add(current_user.candidate)
                
            db.commit()
        elif target_folder == S3Folder.COVER_LETTER:
            if not current_user.candidate:
                raise HTTPException(status_code=400, detail="User is not a candidate and cannot upload a cover letter.")
            
            from app.models.cover_letter import CoverLetter
            existing_cls = db.query(CoverLetter).filter(CoverLetter.candidate_id == current_user.candidate.id).all()
            is_default = len(existing_cls) == 0
            
            new_cl = CoverLetter(
                candidate_id=current_user.candidate.id,
                title=file.filename,
                content=url,
                is_default=is_default
            )
            db.add(new_cl)
            db.commit()

        return {
            "message": "File uploaded successfully",
            "url": url,
            "folder": target_folder.value
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
