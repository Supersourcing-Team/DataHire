from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Type, Any

from app.db.session import get_db
from app.core.dependencies import require_admin
from app.models.taxonomy import TaxonomyDomain, TaxonomyJobRole, TaxonomySkill
from app.schemas.taxonomy import (
    TaxonomyDomainCreate, TaxonomyDomainUpdate, TaxonomyDomainResponse,
    TaxonomyJobRoleCreate, TaxonomyJobRoleUpdate, TaxonomyJobRoleResponse,
    TaxonomySkillCreate, TaxonomySkillUpdate, TaxonomySkillResponse
)

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])

def register_crud_routes(
    api_router: APIRouter,
    path_prefix: str,
    db_model: Type[Any],
    create_schema: Type[Any],
    update_schema: Type[Any],
    response_schema: Type[Any],
    tags: List[str]
):
    @api_router.get(f"{path_prefix}", response_model=List[response_schema], tags=tags)
    def get_all(skip: int = 0, limit: int = 100, include_inactive: bool = False, db: Session = Depends(get_db)):
        query = db.query(db_model)
        if not include_inactive:
            query = query.filter(db_model.is_active == True)
        return query.offset(skip).limit(limit).all()

    @api_router.post(f"{path_prefix}", response_model=response_schema, status_code=status.HTTP_201_CREATED, tags=tags)
    def create(item: create_schema, db: Session = Depends(get_db), current_user = Depends(require_admin)):
        db_item = db_model(**item.model_dump())
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        return db_item
        
    @api_router.get(f"{path_prefix}/{{item_id}}", response_model=response_schema, tags=tags)
    def get_one(item_id: int, db: Session = Depends(get_db)):
        item = db.query(db_model).filter(db_model.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return item
        
    @api_router.put(f"{path_prefix}/{{item_id}}", response_model=response_schema, tags=tags)
    def update(item_id: int, item_update: update_schema, db: Session = Depends(get_db), current_user = Depends(require_admin)):
        db_item = db.query(db_model).filter(db_model.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        update_data = item_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_item, key, value)
            
        db.commit()
        db.refresh(db_item)
        return db_item
        
    @api_router.delete(f"{path_prefix}/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT, tags=tags)
    def soft_delete(item_id: int, db: Session = Depends(get_db), current_user = Depends(require_admin)):
        db_item = db.query(db_model).filter(db_model.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail="Item not found")
            
        db_item.is_active = False
        db.commit()
        return None

# Mapping of route configurations
taxonomy_routes_config = [
    ("/domains", TaxonomyDomain, TaxonomyDomainCreate, TaxonomyDomainUpdate, TaxonomyDomainResponse, ["taxonomy-domains"]),
    ("/job-roles", TaxonomyJobRole, TaxonomyJobRoleCreate, TaxonomyJobRoleUpdate, TaxonomyJobRoleResponse, ["taxonomy-job-roles"]),
    ("/skills", TaxonomySkill, TaxonomySkillCreate, TaxonomySkillUpdate, TaxonomySkillResponse, ["taxonomy-skills"]),
]

# Register all routes
for config in taxonomy_routes_config:
    register_crud_routes(
        api_router=router,
        path_prefix=config[0],
        db_model=config[1],
        create_schema=config[2],
        update_schema=config[3],
        response_schema=config[4],
        tags=config[5]
    )
