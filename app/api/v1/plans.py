from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.dependencies import require_admin
from app.models.meta import MetaSubscriptionPlan
from app.schemas.meta import (
    MetaSubscriptionPlanCreate,
    MetaSubscriptionPlanUpdate,
    MetaSubscriptionPlanResponse
)

# APIRouter definitions using tags=["plans"] to group in plans section in Swagger
job_seeker_plans_router = APIRouter(prefix="/job-seeker/plans", tags=["plans"])
job_poster_plans_router = APIRouter(prefix="/job-poster/plans", tags=["plans"])


# =====================================================================
# Job Seeker Plans Endpoints (/job-seeker/plans)
# =====================================================================

@job_seeker_plans_router.get("", response_model=List[MetaSubscriptionPlanResponse])
def get_job_seeker_plans(db: Session = Depends(get_db)):
    """Retrieve all plans configured for Job Seekers (candidates), including inactive ones."""
    return db.query(MetaSubscriptionPlan).filter(
        MetaSubscriptionPlan.role == "candidate"
    ).order_by(MetaSubscriptionPlan.id).all()


@job_seeker_plans_router.post("", response_model=MetaSubscriptionPlanResponse, status_code=status.HTTP_201_CREATED)
def create_job_seeker_plan(
    item: MetaSubscriptionPlanCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Create a new Job Seeker plan. Enforces role='candidate' (Admin only)."""
    db_item = MetaSubscriptionPlan(**item.model_dump())
    db_item.role = "candidate"
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@job_seeker_plans_router.put("/{id}", response_model=MetaSubscriptionPlanResponse)
def update_job_seeker_plan(
    id: int,
    item_update: MetaSubscriptionPlanUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Update a Job Seeker plan details. Enforces role='candidate' (Admin only)."""
    db_item = db.query(MetaSubscriptionPlan).filter(
        MetaSubscriptionPlan.id == id,
        MetaSubscriptionPlan.role == "candidate"
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Job seeker plan not found")
    
    update_data = item_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)
    db_item.role = "candidate"
        
    db.commit()
    db.refresh(db_item)
    return db_item


@job_seeker_plans_router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_seeker_plan(
    id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Soft delete a Job Seeker plan by deactivating it (Admin only)."""
    db_item = db.query(MetaSubscriptionPlan).filter(
        MetaSubscriptionPlan.id == id,
        MetaSubscriptionPlan.role == "candidate"
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Job seeker plan not found")
        
    db_item.is_active = False
    db.commit()
    return None


# =====================================================================
# Job Poster Plans Endpoints (/job-poster/plans)
# =====================================================================

@job_poster_plans_router.get("", response_model=List[MetaSubscriptionPlanResponse])
def get_job_poster_plans(db: Session = Depends(get_db)):
    """Retrieve all plans configured for Job Posters (employers), including inactive ones."""
    return db.query(MetaSubscriptionPlan).filter(
        MetaSubscriptionPlan.role == "employer"
    ).order_by(MetaSubscriptionPlan.id).all()


@job_poster_plans_router.post("", response_model=MetaSubscriptionPlanResponse, status_code=status.HTTP_201_CREATED)
def create_job_poster_plan(
    item: MetaSubscriptionPlanCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Create a new Job Poster plan. Enforces role='employer' (Admin only)."""
    db_item = MetaSubscriptionPlan(**item.model_dump())
    db_item.role = "employer"
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@job_poster_plans_router.put("/{id}", response_model=MetaSubscriptionPlanResponse)
def update_job_poster_plan(
    id: int,
    item_update: MetaSubscriptionPlanUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Update a Job Poster plan details. Enforces role='employer' (Admin only)."""
    db_item = db.query(MetaSubscriptionPlan).filter(
        MetaSubscriptionPlan.id == id,
        MetaSubscriptionPlan.role == "employer"
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Job poster plan not found")
    
    update_data = item_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)
    db_item.role = "employer"
        
    db.commit()
    db.refresh(db_item)
    return db_item


@job_poster_plans_router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_poster_plan(
    id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin)
):
    """Soft delete a Job Poster plan by deactivating it (Admin only)."""
    db_item = db.query(MetaSubscriptionPlan).filter(
        MetaSubscriptionPlan.id == id,
        MetaSubscriptionPlan.role == "employer"
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Job poster plan not found")
        
    db_item.is_active = False
    db.commit()
    return None
