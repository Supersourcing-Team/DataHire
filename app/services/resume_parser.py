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
        # Using gemini-3.1-flash-lite for fast and structured generation with stable high quota limits
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        
        domains_list_str = ", ".join(f'"{d}"' for d in active_domains)
        
        prompt = f"""
        You are an expert AI Resume Parser. Your task is to analyze the following resume text and parse it into a structured JSON object.
        
        You MUST extract the candidate's total years of experience, a list of their skills, and map their details.
        
        Additionally, review the candidate's profile and recommend the most suitable domain from the following list of active domains:
        [{domains_list_str}]
        
        If none of the domains in the list match, set "recommended_domain" to null.
        
        You MUST return a JSON object with exactly this schema:
        {{
            "total_experience_years": int,
            "skills": ["string"],
            "recommended_domain": "string" or null,
            "structured_data": {{
                "personalInfo": {{
                    "fullName": "string or null",
                    "email": "string or null",
                    "phone": "string or null",
                    "location": "string or null",
                    "linkedin": "string or null",
                    "github": "string or null",
                    "portfolio": "string or null"
                }},
                "summary": {{
                    "text": "string or null"
                }},
                "skills": {{
                    "technical": ["string"],
                    "soft": ["string"],
                    "tools": ["string"]
                }},
                "experience": [
                    {{
                        "id": "string",
                        "company": "string",
                        "role": "string",
                        "location": "string or null",
                        "employmentType": "string or null",
                        "startDate": "YYYY-MM-DD or YYYY-MM or null",
                        "endDate": "YYYY-MM-DD or YYYY-MM or null",
                        "isCurrent": boolean,
                        "bullets": ["string"]
                    }}
                ],
                "education": [
                    {{
                        "id": "string",
                        "institution": "string",
                        "degree": "string",
                        "location": "string or null",
                        "startDate": "YYYY-MM-DD or YYYY-MM or null",
                        "endDate": "YYYY-MM-DD or YYYY-MM or null",
                        "grade": "string or null",
                        "isCurrent": boolean
                    }}
                ],
                "projects": [
                    {{
                        "id": "string",
                        "title": "string",
                        "description": "string or null",
                        "techStack": ["string"],
                        "link": "string or null",
                        "startDate": "YYYY-MM-DD or YYYY-MM or null",
                        "endDate": "YYYY-MM-DD or YYYY-MM or null",
                        "bullets": ["string"]
                    }}
                ],
                "certifications": [
                    {{
                        "id": "string",
                        "title": "string",
                        "issuer": "string",
                        "issueDate": "YYYY-MM-DD or YYYY-MM or null",
                        "expiryDate": "YYYY-MM-DD or YYYY-MM or null",
                        "credentialUrl": "string or null"
                    }}
                ],
                "achievements": [
                    {{
                        "id": "string",
                        "text": "string"
                    }}
                ],
                "languages": [
                    {{
                        "id": "string",
                        "name": "string",
                        "proficiency": "string or null"
                    }}
                ],
                "customSections": [
                    {{
                        "id": "string",
                        "title": "string",
                        "items": [
                            {{
                                "id": "string",
                                "text": "string"
                            }}
                        ]
                    }}
                ]
            }}
        }}
        
        Ensure that the generated JSON object contains all requested fields, extracting the relevant details from the resume text accurately.
        
        --- RESUME TEXT ---
        {text}
        
        Provide the JSON output now:
        """
        
        import time
        max_retries = 3
        retry_delay = 5.0
        
        for attempt in range(max_retries):
            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    ),
                    request_options={"timeout": 60.0}
                )
                parsed_result = json.loads(response.text)
                return parsed_result
            except Exception as e:
                error_msg = str(e)
                if "ResourceExhausted" in error_msg or "Quota exceeded" in error_msg or "429" in error_msg:
                    if attempt < max_retries - 1:
                        logger.warning(f"Gemini rate limit hit. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                logger.error(f"Gemini resume parsing failed: {e}")
                break
                
        # If we broke out of loop or retries failed, return fallback schema
        return {
            "total_experience_years": 0,
            "skills": [],
            "recommended_domain": None,
            "structured_data": {
                "personalInfo": {
                    "fullName": None,
                    "email": None,
                    "phone": None,
                    "location": None,
                    "linkedin": None,
                    "github": None,
                    "portfolio": None
                },
                "summary": {
                    "text": text[:1000] if text else ""
                },
                "skills": {
                    "technical": [],
                    "soft": [],
                    "tools": []
                },
                "experience": [],
                "education": [],
                "projects": [],
                "certifications": [],
                "achievements": [],
                "languages": [],
                "customSections": []
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
        structured_data = parse_result.get("structured_data") or {}
        
        # Deactivate existing primary resumes if new one is primary
        if is_primary:
            db.query(Resume).filter(Resume.candidate_id == candidate.id).update({Resume.is_primary: False})
            
        new_resume = Resume(
            candidate_id=candidate.id,
            file_url=file_url,
            file_name=file_name,
            is_primary=is_primary,
            is_ai_optimized=False,
            version_number=existing_resumes_count + 1,
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
            
        # 7. Update Candidate taxonomy domain if primary
        if is_primary and domain_id:
            candidate.taxonomy_domain_id = domain_id
            db.add(candidate)
            
        db.commit()
        db.refresh(new_resume)
        
        return new_resume

# Singleton instance
resume_parser_service = ResumeParserService()
