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
    folder: S3Folder = Form(..., description="The S3 folder to store the file in"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload a file to a specific folder in S3. If it's a resume, it is parsed and saved.
    """
    try:
        url = await s3_service.upload_file(file, folder)
        
        if folder == S3Folder.RESUME:
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
            
            new_resume = Resume(
                candidate_id=current_user.candidate.id,
                file_url=url,
                file_name=file.filename,
                is_primary=is_primary,
                version_number=len(existing_resumes) + 1,
                total_experience_years=total_exp,
                taxonomy_domain_id=domain_id,
                extracted_skills=skills
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
                    
                new_section = ResumeSection(
                    section_type=matched_sec_type.value,
                    original_content=sec_content
                )
                new_resume.sections.append(new_section)
                
            db.add(new_resume)
            
            # Update candidate taxonomy domain if primary
            if is_primary and domain_id:
                current_user.candidate.taxonomy_domain_id = domain_id
                db.add(current_user.candidate)
                
            db.commit()

        return {
            "message": "File uploaded successfully",
            "url": url,
            "folder": folder.value
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
