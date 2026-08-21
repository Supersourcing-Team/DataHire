import logging
from sqlalchemy.orm import Session
from app.models.candidate import Candidate
from app.models.job import JobPosting
from app.models.cover_letter import CoverLetter
from app.models.resume import Resume
from app.core.config import settings

logger = logging.getLogger(__name__)

def generate_cover_letter_text(candidate: Candidate, job: JobPosting, resume: Resume) -> str:
    import google.generativeai as genai
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    company_name = job.company.name if job.company else "Target Company"
    company_desc = job.company.description if (job.company and job.company.description) else "A leading innovator in the industry."
    job_overview = job.job_overview or job.description or ""
    if isinstance(job.about_role, list):
        about_role = "\n".join(f"- {r}" for r in job.about_role)
    else:
        about_role = job.about_role or ""
    requirements_str = "\n".join(f"- {r}" for r in job.requirements) if (job.requirements and isinstance(job.requirements, list)) else ""
    responsibilities_str = "\n".join(f"- {r}" for r in job.responsibilities) if (job.responsibilities and isinstance(job.responsibilities, list)) else ""
    work_mode_str = job.work_mode.name if job.work_mode else "Not specified"
    total_exp = f"{resume.total_experience_years} years" if resume.total_experience_years else "Not specified"
    resume_skills = ", ".join(resume.extracted_skills) if resume.extracted_skills else "None"

    prompt = f"""
    You are an expert career assistant. Generate a highly professional, compelling, and customized cover letter for:
    
    --- TARGET COMPANY ---
    Name: {company_name}
    About Company: {company_desc}
    
    --- JOB POSITION ---
    Title: {job.title}
    Work Mode: {work_mode_str}
    Job Overview: {job_overview}
    About the Role: {about_role}
    
    Requirements:
    {requirements_str}
    
    Responsibilities:
    {responsibilities_str}
    
    --- CANDIDATE PROFILE ---
    Name: {candidate.full_name}
    Total Experience: {total_exp}
    Skills: {resume_skills}
    
    Generate a cover letter customized to match the candidate's skills and experience to the target company's business domain and the job's responsibilities/requirements. 
    The tone should be professional, warm, confident, and highly tailored. Avoid generic platitudes. Output only the cover letter body.
    """
    
    response = model.generate_content(prompt)
    return response.text

def generate_and_save_cover_letter(candidate: Candidate, job: JobPosting, resume: Resume, db: Session) -> CoverLetter:
    """
    Generates cover letter text using Gemini API, creates a CoverLetter DB record,
    and updates candidate's monthly cover letters generated count.
    Does NOT commit the transaction to allow it to be committed by the caller.
    """
    from app.services.plans_service import PLAN_LIMITS
    tier = (candidate.plan_tier or "free").lower()
    limits = PLAN_LIMITS.get_limits(tier, db)
    if limits.get("monthly_cover_letter_limit", 0) <= 0:
        raise ValueError("Cover letter generation is not allowed on the Free plan.")
        
    if limits.get("monthly_cover_letter_limit", 0) < 9999:
        if candidate.cover_letters_generated_this_month >= limits.get("monthly_cover_letter_limit", 0):
            raise ValueError("Candidate has reached their monthly cover letter generation limit.")

    cover_letter_text = generate_cover_letter_text(candidate, job, resume)
    
    new_cover_letter = CoverLetter(
        candidate_id=candidate.id,
        job_id=job.id,
        title=f"{job.title} Cover Letter",
        content=cover_letter_text,
        cover_letter_url=None,
        is_default=False
    )
    db.add(new_cover_letter)
    candidate.cover_letters_generated_this_month += 1
    db.add(candidate)
    
    return new_cover_letter

def extract_and_clean_cover_letter(file_url: str, file_name: str = None) -> str:
    """
    Downloads the cover letter file from the given S3 or HTTP URL, extracts its raw text
    (supports PDF and DOCX), and uses Gemini (gemini-3.1-flash-lite) to clean and format
    the core cover letter content.
    """
    from app.services.resume_parser import resume_parser_service
    import google.generativeai as genai
    
    # 1. Download file bytes
    logger.info(f"Downloading cover letter file from URL: {file_url}")
    try:
        file_bytes = resume_parser_service.download_file(file_url)
    except Exception as e:
        logger.error(f"Failed to download cover letter from {file_url}: {e}")
        raise RuntimeError(f"Failed to download cover letter file: {str(e)}")
        
    # 2. Determine file type and extract raw text
    ext = ""
    target_name = file_name or file_url or ""
    if "." in target_name:
        ext = target_name.split(".")[-1].lower().split("?")[0]
        
    logger.info(f"Extracting raw text for cover letter with extension: {ext}")
    try:
        if ext == "docx":
            raw_text = resume_parser_service.extract_text_from_docx(file_bytes)
        elif ext == "pdf" or not ext:
            # Default to PDF extraction
            raw_text = resume_parser_service.extract_text_from_pdf(file_bytes)
        else:
            # For other text files, try decoding, else fallback to PDF parser
            try:
                raw_text = file_bytes.decode('utf-8')
            except Exception:
                raw_text = resume_parser_service.extract_text_from_pdf(file_bytes)
    except Exception as e:
        logger.error(f"Failed to extract raw text from cover letter file: {e}")
        raise RuntimeError(f"Failed to parse cover letter file structure: {str(e)}")
        
    if not raw_text or not raw_text.strip():
        raise ValueError("The cover letter file is empty or contains no readable text.")
        
    # 3. Clean and extract cover letter text via Gemini (gemini-3.1-flash-lite)
    logger.info("Cleaning raw cover letter text using Gemini...")
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        
        prompt = f"""
        You are an expert career assistant and document parser.
        Your task is to extract the clean, formatted cover letter content from the following raw text of a document.
        Remove any irrelevant headers, footers, page numbers, metadata, or document artifacts.
        Output ONLY the clean, formatted body text of the cover letter. Do not include any intro/outro explanations, quotes, or markdown code block markers around your response (unless they are part of the cover letter text itself).
        
        --- RAW TEXT ---
        {raw_text}
        """
        
        response = model.generate_content(prompt)
        cleaned_content = response.text
        if cleaned_content:
            cleaned_content = cleaned_content.strip()
        else:
            cleaned_content = raw_text.strip()
        return cleaned_content
    except Exception as e:
        logger.error(f"Gemini cleaning failed: {e}")
        # Fall back to raw text if Gemini cleaning fails
        return raw_text.strip()
