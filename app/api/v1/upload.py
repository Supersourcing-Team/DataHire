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
            from app.api.v1.job_seeker import PLAN_LIMITS
            tier = current_user.candidate.plan_tier or "free"
            limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
            
            existing_resumes = db.query(Resume).filter(
                Resume.candidate_id == current_user.candidate.id,
                Resume.is_deleted == False
            ).all()
            
            if len(existing_resumes) >= limits["saved_resumes_limit"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"You have reached your limit of {limits['saved_resumes_limit']} saved resumes. Please delete an existing resume to upload a new one."
                )
            
            is_primary = len(existing_resumes) == 0
            
            if is_primary:
                db.query(Resume).filter(Resume.candidate_id == current_user.candidate.id).update({Resume.is_primary: False})
            
            total_exp = parse_result.get("total_experience_years", 0)
            skills = parse_result.get("skills", [])
            structured_data = parse_result.get("structured_data") or {}
            
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
            
            # Build sections_dict dynamically in Python from structured_data
            sections_dict = {}
            
            summary_text = structured_data.get("summary", {}).get("text", "")
            if summary_text:
                sections_dict[SectionType.SUMMARY] = (summary_text, structured_data.get("summary"))
                
            exp_list = structured_data.get("experience", [])
            if exp_list:
                exp_strs = []
                for exp in exp_list:
                    company = exp.get("company", "N/A")
                    role = exp.get("role", "N/A")
                    location = exp.get("location")
                    dates = f"{exp.get('startDate', '')} - {exp.get('endDate') or 'Present'}"
                    bullets = "\n".join(f"- {b}" for b in exp.get("bullets", []))
                    item_str = f"{role} at {company}"
                    if location:
                        item_str += f" ({location})"
                    item_str += f"\n{dates}\n{bullets}"
                    exp_strs.append(item_str)
                sections_dict[SectionType.EXPERIENCE] = ("\n\n".join(exp_strs), exp_list)
                
            edu_list = structured_data.get("education", [])
            if edu_list:
                edu_strs = []
                for edu in edu_list:
                    inst = edu.get("institution", "N/A")
                    degree = edu.get("degree", "N/A")
                    grade = edu.get("grade")
                    dates = f"{edu.get('startDate', '')} - {edu.get('endDate') or 'Present'}"
                    item_str = f"{degree} from {inst} ({dates})"
                    if grade:
                        item_str += f" | Grade: {grade}"
                    edu_strs.append(item_str)
                sections_dict[SectionType.EDUCATION] = ("\n\n".join(edu_strs), edu_list)
                
            proj_list = structured_data.get("projects", [])
            if proj_list:
                proj_strs = []
                for proj in proj_list:
                    title = proj.get("title", "N/A")
                    desc = proj.get("description", "")
                    tech = ", ".join(proj.get("techStack", []))
                    bullets = "\n".join(f"- {b}" for b in proj.get("bullets", []))
                    item_str = f"Project: {title}"
                    if tech:
                        item_str += f" [Tech: {tech}]"
                    if desc:
                        item_str += f"\n{desc}"
                    if bullets:
                        item_str += f"\n{bullets}"
                    proj_strs.append(item_str)
                sections_dict[SectionType.PROJECTS] = ("\n\n".join(proj_strs), proj_list)
                
            skills_data = structured_data.get("skills", {})
            if skills_data:
                tech_s = ", ".join(skills_data.get("technical", []))
                soft_s = ", ".join(skills_data.get("soft", []))
                tools_s = ", ".join(skills_data.get("tools", []))
                skills_parts = []
                if tech_s:
                    skills_parts.append(f"Technical Skills: {tech_s}")
                if soft_s:
                    skills_parts.append(f"Soft Skills: {soft_s}")
                if tools_s:
                    skills_parts.append(f"Tools: {tools_s}")
                if skills_parts:
                    sections_dict[SectionType.SKILLS] = ("\n".join(skills_parts), skills_data)
                    
            cert_list = structured_data.get("certifications", [])
            if cert_list:
                cert_strs = []
                for cert in cert_list:
                    title = cert.get("title", "N/A")
                    issuer = cert.get("issuer", "N/A")
                    issue_date = cert.get("issueDate", "")
                    cert_strs.append(f"{title} by {issuer} ({issue_date})")
                sections_dict[SectionType.CERTIFICATIONS] = ("\n".join(cert_strs), cert_list)
                
            other_parts = []
            achievements = structured_data.get("achievements", [])
            if achievements:
                other_parts.append("Achievements:\n" + "\n".join(f"- {a.get('text', '')}" for a in achievements))
            languages = structured_data.get("languages", [])
            if languages:
                other_parts.append("Languages:\n" + "\n".join(f"- {l.get('name', '')} ({l.get('proficiency', 'N/A')})" for l in languages))
            custom_sections = structured_data.get("customSections", [])
            for cs in custom_sections:
                title = cs.get("title", "Custom Section")
                items = cs.get("items", [])
                other_parts.append(f"{title}:\n" + "\n".join(f"- {i.get('text', '')}" for i in items))
            if other_parts:
                sections_dict[SectionType.OTHER] = ("\n\n".join(other_parts), {
                    "achievements": achievements,
                    "languages": languages,
                    "customSections": custom_sections
                })

            # Save constructed sections to new_resume
            for sec_type, (sec_content, sec_struct) in sections_dict.items():
                new_section = ResumeSection(
                    section_type=sec_type.value,
                    original_content=sec_content,
                    structured_content=sec_struct
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
