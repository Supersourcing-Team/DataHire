from sqlalchemy import event
from sqlalchemy.orm import Mapper
from sqlalchemy.engine import Connection
from app.services.embedding_service import embedding_service
from app.db.base_class import Base

def _get_text_to_embed(target) -> str:
    parts = []
    # Common text fields to embed
    for field in ["name", "title", "description", "original_content", "job_overview"]:
        if hasattr(target, field) and getattr(target, field):
            parts.append(str(getattr(target, field)))
            
    # Check array fields like aliases and extracted_skills
    if hasattr(target, "aliases") and getattr(target, "aliases"):
        aliases = getattr(target, "aliases")
        if isinstance(aliases, list):
            parts.append(" ".join(str(a) for a in aliases))
            
    if hasattr(target, "extracted_skills") and getattr(target, "extracted_skills"):
        skills = getattr(target, "extracted_skills")
        if isinstance(skills, list):
            parts.append(" ".join(str(s) for s in skills))
            
    # Check associated sections (e.g. Resume.sections)
    if hasattr(target, "sections") and getattr(target, "sections"):
        sections = getattr(target, "sections")
        if isinstance(sections, list):
            for sec in sections:
                content = getattr(sec, "optimized_content", None) or getattr(sec, "original_content", None)
                if content:
                    parts.append(str(content))
            
    # Check job sections list fields
    for field in ["requirements", "responsibilities", "benefits", "about_role"]:
        if hasattr(target, field) and getattr(target, field):
            items = getattr(target, field)
            if isinstance(items, list):
                parts.append(" ".join(str(i) for i in items))
            elif isinstance(items, str):
                parts.append(items)
            
    return " ".join(parts)

def generate_target_embedding(mapper: Mapper, connection: Connection, target: Base):
    from app.models.job import JobPosting
    from app.models.resume import Resume
    
    if isinstance(target, Resume) and target.is_ai_optimized and target.overall_embedding is not None:
        return
        
    # Auto-generate description for JobPosting if empty
    if isinstance(target, JobPosting) and not getattr(target, "description"):
        sections = []
        job_overview = getattr(target, "job_overview")
        about_role = getattr(target, "about_role")
        requirements = getattr(target, "requirements")
        responsibilities = getattr(target, "responsibilities")
        benefits = getattr(target, "benefits")
        
        if job_overview:
            sections.append(f"Job Overview:\n{job_overview}")
        if about_role:
            if isinstance(about_role, list):
                sections.append("About the Role:\n" + "\n".join(f"- {r}" for r in about_role))
            else:
                sections.append(f"About the Role:\n{about_role}")
        if requirements and isinstance(requirements, list):
            sections.append("Requirements:\n" + "\n".join(f"- {r}" for r in requirements))
        if responsibilities and isinstance(responsibilities, list):
            sections.append("Responsibilities:\n" + "\n".join(f"- {r}" for r in responsibilities))
        if benefits and isinstance(benefits, list):
            sections.append("Benefits:\n" + "\n".join(f"- {b}" for b in benefits))
            
        if sections:
            target.description = "\n\n".join(sections)
        else:
            target.description = getattr(target, "title", "")

    # Extract skills for JobPosting if text fields modified or empty
    if isinstance(target, JobPosting):
        from sqlalchemy.orm import attributes
        desc_changed = attributes.get_history(target, 'description').has_changes()
        overview_changed = attributes.get_history(target, 'job_overview').has_changes()
        req_changed = attributes.get_history(target, 'requirements').has_changes()
        title_changed = attributes.get_history(target, 'title').has_changes()
        
        if desc_changed or overview_changed or req_changed or title_changed or not target.extracted_skills:
            text_parts = []
            if target.title:
                text_parts.append(f"Title: {target.title}")
            if target.job_overview:
                text_parts.append(f"Job Overview:\n{target.job_overview}")
            if target.description:
                text_parts.append(f"Description:\n{target.description}")
            if target.requirements:
                if isinstance(target.requirements, list):
                    text_parts.append("Requirements:\n" + "\n".join(target.requirements))
                else:
                    text_parts.append(f"Requirements:\n{target.requirements}")
            
            combined_text = "\n\n".join(text_parts)
            if combined_text.strip():
                from app.services.resume_parser import resume_parser_service
                skills = resume_parser_service.extract_skills_from_jd(combined_text)
                if skills:
                    target.extracted_skills = skills

    text = _get_text_to_embed(target)
    if not text:
        return
        
    embedding = embedding_service.get_embedding(text)
    
    if hasattr(target, "embedding"):
        target.embedding = embedding
        
    if hasattr(target, "overall_embedding"):
        target.overall_embedding = embedding

def register_embedding_listeners():
    from app.models.job import JobPosting
    from app.models.resume import Resume
    from app.models.taxonomy import TaxonomyDomain, TaxonomyJobRole, TaxonomySkill
    
    models_with_embeddings = [JobPosting, Resume, TaxonomyDomain, TaxonomyJobRole, TaxonomySkill]
    
    for model in models_with_embeddings:
        event.listen(model, 'before_insert', generate_target_embedding)
        event.listen(model, 'before_update', generate_target_embedding)
