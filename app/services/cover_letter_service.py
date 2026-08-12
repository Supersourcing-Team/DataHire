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

def generate_and_save_cover_letter(candidate: Candidate, job: JobPosting, resume: Resume, db: Session) -> str:
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
        is_default=False
    )
    db.add(new_cover_letter)
    candidate.cover_letters_generated_this_month += 1
    db.add(candidate)
    
    return cover_letter_text
