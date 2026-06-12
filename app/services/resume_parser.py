import io
import json
import logging
from typing import Dict, Any, List, Optional
import httpx
import PyPDF2
import google.generativeai as genai
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.resume import Resume, ResumeSection, SectionType
from app.models.candidate import Candidate
from app.models.taxonomy import TaxonomyDomain
from app.services.s3_service import S3Service

logger = logging.getLogger(__name__)

class ResumeParserService:
    def download_file(self, url: str) -> bytes:
        """
        Downloads a file from S3 using the S3 client, or falls back to an HTTP download.
        """
        try:
            # Try parsing S3 URL and downloading via boto3 client
            s3_service = S3Service()
            if s3_service.bucket_name:
                s3_key = s3_service.extract_key(url)
                response = s3_service.s3_client.get_object(
                    Bucket=s3_service.bucket_name,
                    Key=s3_key
                )
                return response['Body'].read()
        except Exception as e:
            logger.warning(f"S3 download failed, falling back to HTTP: {e}")
        
        # Fallback to direct HTTP download
        try:
            response = httpx.get(url, timeout=10.0)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"HTTP download failed: {e}")
            raise RuntimeError(f"Failed to download file from URL: {url}. Error: {e}")

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """
        Extracts plain text from PDF file bytes using PyPDF2.
        """
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise RuntimeError(f"Failed to extract text from PDF: {e}")

    def parse_resume_text(self, text: str, active_domains: List[str]) -> Dict[str, Any]:
        """
        Sends the extracted resume text to Gemini to parse into structured JSON.
        """
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # Using gemini-2.5-flash for fast and structured generation
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        domains_list_str = ", ".join(f'"{d}"' for d in active_domains)
        
        prompt = f"""
        You are an expert AI Resume Parser. Your task is to analyze the following resume text and parse it into a structured JSON object.
        
        You MUST extract the candidate's total years of experience, a list of their skills, and map their details to the standard resume sections:
        - Summary
        - Experience
        - Education
        - Projects
        - Skills
        - Certifications
        - Other (use this for any content that doesn't fit the above categories)
        
        Additionally, review the candidate's profile and recommend the most suitable domain from the following list of active domains:
        [{domains_list_str}]
        
        If none of the domains in the list match, set "recommended_domain" to null.
        
        You MUST return a JSON object with exactly this schema:
        {{
            "total_experience_years": int,
            "skills": ["string"],
            "recommended_domain": "string" or null,
            "sections": {{
                "Summary": "string or null",
                "Experience": "string or null",
                "Education": "string or null",
                "Projects": "string or null",
                "Skills": "string or null",
                "Certifications": "string or null",
                "Other": "string or null"
            }}
        }}
        
        Ensure that the "sections" values contain the raw, unmodified text content belonging to each section extracted from the resume. Do not rewrite, summarize, or translate the content.
        
        --- RESUME TEXT ---
        {text}
        
        Provide the JSON output now:
        """
        
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                ),
                request_options={"timeout": 15.0}
            )
            parsed_result = json.loads(response.text)
            return parsed_result
        except Exception as e:
            logger.error(f"Gemini resume parsing failed: {e}")
            # Return a basic structure as fallback
            return {
                "total_experience_years": 0,
                "skills": [],
                "recommended_domain": None,
                "sections": {
                    "Summary": text[:1000] if text else "",
                    "Other": text
                }
            }

    def parse_and_save_resume(
        self,
        db: Session,
        candidate: Candidate,
        file_url: str,
        file_name: str,
        is_primary: bool
    ) -> Resume:
        """
        Orchestration method that downloads, parses, and saves a resume into DB.
        """
        logger.info(f"Parsing resume for candidate {candidate.id} from {file_url}")
        
        # 1. Download file
        pdf_bytes = self.download_file(file_url)
        
        # 2. Extract text
        text = self.extract_text_from_pdf(pdf_bytes)
        if not text or not text.strip():
            raise ValueError("The PDF file contains no readable text.")
            
        # 3. Get active taxonomy domains
        domains = db.query(TaxonomyDomain).filter(TaxonomyDomain.is_active == True).all()
        active_domain_names = [d.name for d in domains]
        
        # 4. Parse via Gemini
        parse_result = self.parse_resume_text(text, active_domain_names)
        
        # 5. Resolve taxonomy domain
        recommended_domain_name = parse_result.get("recommended_domain")
        domain_id = None
        if recommended_domain_name:
            matched_domain = next((d for d in domains if d.name.lower() == recommended_domain_name.lower()), None)
            if matched_domain:
                domain_id = matched_domain.id
                
        # 6. Create Resume
        existing_resumes_count = db.query(Resume).filter(Resume.candidate_id == candidate.id).count()
        
        total_exp = parse_result.get("total_experience_years", 0)
        skills = parse_result.get("skills", [])
        
        # Deactivate existing primary resumes if new one is primary
        if is_primary:
            db.query(Resume).filter(Resume.candidate_id == candidate.id).update({Resume.is_primary: False})
            
        new_resume = Resume(
            candidate_id=candidate.id,
            file_url=file_url,
            file_name=file_name,
            is_primary=is_primary,
            version_number=existing_resumes_count + 1,
            total_experience_years=total_exp,
            taxonomy_domain_id=domain_id,
            extracted_skills=skills
        )
        
        # Create Resume Sections and link them to new_resume before adding to db
        sections_dict = parse_result.get("sections", {}) or {}
        for sec_name, sec_content in sections_dict.items():
            if not sec_content or not sec_content.strip():
                continue
                
            # Find closest matching SectionType
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
            
        # 7. Update Candidate taxonomy domain if primary
        if is_primary and domain_id:
            candidate.taxonomy_domain_id = domain_id
            db.add(candidate)
            
        db.commit()
        db.refresh(new_resume)
        
        return new_resume

# Singleton instance
resume_parser_service = ResumeParserService()
