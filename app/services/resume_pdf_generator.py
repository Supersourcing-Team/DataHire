import logging
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.resume import Resume, ResumeSection
from app.models.candidate import Candidate
from app.services.pdf_service import pdf_service
from app.services.s3_service import S3Service, S3Folder, clean_s3_url

s3_service = S3Service()

logger = logging.getLogger(__name__)


def render_resume_to_html(structured_data: Dict[str, Any], default_name: str = "Candidate") -> str:
    """
    Renders structured resume JSON data into a clean, modern HTML document
    compatible with xhtml2pdf engine, matching the user's specific B&W minimal layout.
    """
    if not structured_data:
        structured_data = {}

    personal_info = structured_data.get("personalInfo", {})
    full_name = personal_info.get("fullName") or default_name
    email = personal_info.get("email") or ""
    phone = personal_info.get("phone") or ""
    location = personal_info.get("location") or ""
    linkedin = personal_info.get("linkedin") or ""
    portfolio = personal_info.get("portfolio") or ""

    contact_parts = [p for p in [email, phone, location, linkedin, portfolio] if p]
    contact_line = " | ".join(contact_parts)

    summary_obj = structured_data.get("summary", {})
    summary_text = summary_obj.get("text", "") if isinstance(summary_obj, dict) else str(summary_obj or "")

    skills_obj = structured_data.get("skills", {})
    technical_skills = []
    soft_skills = []
    tools = []
    if isinstance(skills_obj, dict):
        technical_skills = skills_obj.get("technical", []) or []
        soft_skills = skills_obj.get("soft", []) or []
        tools = skills_obj.get("tools", []) or []
    elif isinstance(skills_obj, list):
        technical_skills = skills_obj

    all_skills = list(dict.fromkeys(technical_skills + soft_skills + tools))

    experience_list = structured_data.get("experience", []) or []
    education_list = structured_data.get("education", []) or []
    projects_list = structured_data.get("projects", []) or []
    certifications_list = structured_data.get("certifications", []) or []

    # Build HTML sections
    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
    @page {
        size: letter portrait;
        margin: 0.5in;
    }
    body {
        font-family: Helvetica, Arial, sans-serif;
        font-size: 10pt;
        line-height: 1.4;
        color: #222222;
    }
    .header {
        text-align: center;
        margin-bottom: 12px;
    }
    .name {
        font-size: 22pt;
        font-weight: bold;
        color: #000000;
        margin-bottom: 4px;
        letter-spacing: 0.5px;
    }
    .contact {
        font-size: 9.5pt;
        color: #4b5563;
        text-decoration: none;
    }
    .contact a {
        color: #4b5563;
        text-decoration: underline;
    }
    .section-title {
        font-size: 11pt;
        font-weight: bold;
        color: #000000;
        border-bottom: 1px solid #cbd5e1;
        padding-bottom: 3px;
        margin-top: 14px;
        margin-bottom: 6px;
        text-transform: uppercase;
    }
    .summary-text {
        font-size: 10pt;
        color: #222222;
        margin-bottom: 10px;
        text-align: justify;
    }
    .item-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 6px;
        margin-bottom: 2px;
    }
    .item-table td {
        padding: 0;
        vertical-align: top;
        border: none;
    }
    .item-left {
        text-align: left;
        font-size: 10pt;
    }
    .item-right {
        text-align: right;
        font-size: 9.5pt;
        color: #4b5563;
        width: 150px;
    }
    .gpa-text {
        font-size: 9.5pt;
        color: #334155;
        margin-bottom: 6px;
        margin-top: 2px;
    }
    .item-header-no-date {
        margin-top: 6px;
        margin-bottom: 2px;
        font-size: 10pt;
    }
    ul {
        margin-top: 3px;
        margin-bottom: 6px;
        padding-left: 18px;
    }
    li {
        font-size: 9.5pt;
        color: #222222;
        margin-bottom: 3px;
    }
    .skills-container {
        font-size: 10pt;
        color: #222222;
        margin-top: 4px;
    }
</style>
</head>
<body>
""")

    # Header
    html_parts.append('<div class="header">')
    html_parts.append(f'<div class="name">{full_name}</div>')
    if contact_line:
        html_parts.append(f'<div class="contact">{contact_line}</div>')
    html_parts.append('</div>')

    # Summary
    if summary_text:
        html_parts.append('<div class="section-title">Professional Summary</div>')
        html_parts.append(f'<div class="summary-text">{summary_text}</div>')

    # Experience
    if experience_list:
        html_parts.append('<div class="section-title">Work Experience</div>')
        for exp in experience_list:
            role = exp.get("role") or exp.get("title") or "Position"
            company = exp.get("company") or exp.get("organization") or ""
            location = exp.get("location") or ""
            dates = f"{exp.get('startDate', '')} - {exp.get('endDate', 'Present' if exp.get('isCurrent') else '')}".strip(" -")
            
            company_loc_parts = []
            if company and company != "N/A":
                company_loc_parts.append(company)
            if location:
                company_loc_parts.append(location)
            
            company_loc_str = ""
            if company_loc_parts:
                if len(company_loc_parts) > 1:
                    company_loc_str = f"{company_loc_parts[0]} ({company_loc_parts[1]})"
                else:
                    company_loc_str = company_loc_parts[0]
            
            left_html = f'<strong>{role}</strong>'
            if company_loc_str:
                left_html += f', <span style="font-style: italic; color: #333333;">{company_loc_str}</span>'
            
            html_parts.append(f"""
            <table class="item-table">
                <tr>
                    <td class="item-left">{left_html}</td>
                    <td class="item-right">{dates}</td>
                </tr>
            </table>
            """)

            bullets = exp.get("bullets") or []
            if isinstance(bullets, str):
                bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
            if bullets:
                html_parts.append('<ul>')
                for b in bullets:
                    cleaned_b = re.sub(r'^[•\-*\d\.\s]+', '', str(b)).strip()
                    if cleaned_b:
                        html_parts.append(f'<li>{cleaned_b}</li>')
                html_parts.append('</ul>')

    # Education
    if education_list:
        html_parts.append('<div class="section-title">Education</div>')
        for edu in education_list:
            degree = edu.get("degree") or "Degree"
            inst = edu.get("institution") or edu.get("school") or ""
            location = edu.get("location") or ""
            dates = f"{edu.get('startDate', '')} - {edu.get('endDate', '')}".strip(" -")
            gpa = edu.get("grade") or edu.get("gpa") or ""
            
            inst_loc_parts = []
            if inst and inst != "N/A":
                inst_loc_parts.append(inst)
            if location:
                inst_loc_parts.append(location)
                
            inst_loc_str = ""
            if inst_loc_parts:
                if len(inst_loc_parts) > 1:
                    inst_loc_str = f"{inst_loc_parts[0]} ({inst_loc_parts[1]})"
                else:
                    inst_loc_str = inst_loc_parts[0]
            
            left_html = f'<strong>{degree}</strong>'
            if inst_loc_str:
                left_html += f', <span style="font-style: italic; color: #333333;">{inst_loc_str}</span>'
                
            html_parts.append(f"""
            <table class="item-table">
                <tr>
                    <td class="item-left">{left_html}</td>
                    <td class="item-right">{dates}</td>
                </tr>
            </table>
            """)
            if gpa:
                html_parts.append(f'<div class="gpa-text">GPA: {gpa}</div>')

    # Projects
    if projects_list:
        html_parts.append('<div class="section-title">Projects</div>')
        for proj in projects_list:
            title = proj.get("title") or "Project"
            desc = proj.get("description") or ""
            bullets = proj.get("bullets") or []
            tech = proj.get("techStack") or []
            dates = f"{proj.get('startDate', '')} - {proj.get('endDate', '')}".strip(" -")
            
            tech_str = ""
            if tech:
                tech_str = ", ".join(tech) if isinstance(tech, list) else str(tech)
                tech_str = f' <span style="font-weight: normal; color: #555555; font-size: 9.5pt;">({tech_str})</span>'
            
            left_html = f'<strong>{title}</strong>{tech_str}'
            
            if dates:
                html_parts.append(f"""
                <table class="item-table">
                    <tr>
                        <td class="item-left">{left_html}</td>
                        <td class="item-right">{dates}</td>
                    </tr>
                </table>
                """)
            else:
                html_parts.append(f'<div class="item-header-no-date">{left_html}</div>')
                
            if desc:
                html_parts.append(f'<div class="summary-text">{desc}</div>')

            if isinstance(bullets, str):
                bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
            if bullets:
                html_parts.append('<ul>')
                for b in bullets:
                    cleaned_b = re.sub(r'^[•\-*\d\.\s]+', '', str(b)).strip()
                    if cleaned_b:
                        html_parts.append(f'<li>{cleaned_b}</li>')
                html_parts.append('</ul>')

    # Skills
    if all_skills:
        skills_str = ", ".join(all_skills)
        html_parts.append('<div class="section-title">Skills</div>')
        html_parts.append(f'<div class="skills-container"><strong>Technical Skills:</strong> {skills_str}</div>')

    # Certifications
    if certifications_list:
        html_parts.append('<div class="section-title">Certifications</div>')
        html_parts.append('<ul>')
        for cert in certifications_list:
            title = cert.get("title") if isinstance(cert, dict) else str(cert)
            if title:
                html_parts.append(f'<li>{title}</li>')
        html_parts.append('</ul>')

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


async def generate_and_save_optimized_resume_pdf(db: Session, resume: Resume, candidate: Candidate) -> str:
    """
    Renders structured resume data into PDF format, uploads it to S3,
    and returns the clean static S3 URL.
    """
    try:
        candidate_name = candidate.full_name or "Candidate"
        html_content = render_resume_to_html(resume.structured_data, default_name=candidate_name)
        
        pdf_bytes = pdf_service.convert_html_to_pdf(html_content)
        
        filename = f"optimized_resume_{resume.id}.pdf"
        s3_presigned_url = await s3_service.upload_bytes(
            contents=pdf_bytes,
            filename=filename,
            folder=S3Folder.RESUME,
            content_type="application/pdf"
        )
        
        clean_url = clean_s3_url(s3_presigned_url)
        logger.info("Successfully generated and saved optimized resume PDF to S3: %s", clean_url)
        return clean_url
    except Exception as e:
        logger.error("Failed to generate and save optimized resume PDF for resume %s: %s", resume.id, e, exc_info=True)
        # Fallback to current file_url if PDF rendering/upload fails
        return resume.file_url
