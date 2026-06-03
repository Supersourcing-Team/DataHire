from sqlalchemy import event
from sqlalchemy.orm import Mapper
from sqlalchemy.engine import Connection
from app.services.embedding_service import embedding_service
from app.db.base_class import Base

def _get_text_to_embed(target) -> str:
    parts = []
    # Common text fields to embed
    for field in ["name", "title", "description", "original_content"]:
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
            
    return " ".join(parts)

def generate_target_embedding(mapper: Mapper, connection: Connection, target: Base):
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
