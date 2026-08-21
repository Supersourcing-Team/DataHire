import logging
from typing import Optional, Any, Dict
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class DynamicPlanLimits(dict):
    def __init__(self, role: str):
        self.role = role
        # Seed default plan values for backward compatibility and fallback
        if role == "candidate":
            super().__init__({
                "free": {
                    "name": "Free",
                    "daily_apply_limit": 0,
                    "monthly_ai_credits": 75,
                    "monthly_resume_optimization_limit": 3,
                    "monthly_cover_letter_limit": 0,
                    "missing_skills_analysis_enabled": False,
                    "saved_resumes_limit": 7,
                    "resume_upload_limits": 3
                },
                "silver": {
                    "name": "Silver",
                    "daily_apply_limit": 3,
                    "monthly_ai_credits": 800,
                    "monthly_resume_optimization_limit": 15,
                    "monthly_cover_letter_limit": 15,
                    "missing_skills_analysis_enabled": True,
                    "saved_resumes_limit": 12,
                    "resume_upload_limits": 5
                },
                "gold": {
                    "name": "Gold",
                    "daily_apply_limit": 5,
                    "monthly_ai_credits": 1200,
                    "monthly_resume_optimization_limit": 22,
                    "monthly_cover_letter_limit": 22,
                    "missing_skills_analysis_enabled": True,
                    "saved_resumes_limit": 15,
                    "resume_upload_limits":10
                },
                "platinum": {
                    "name": "Platinum",
                    "daily_apply_limit": 9999,
                    "monthly_ai_credits": 99999,
                    "monthly_resume_optimization_limit": 50,
                    "monthly_cover_letter_limit": 1000,
                    "missing_skills_analysis_enabled": True,
                    "saved_resumes_limit": 100,
                    "resume_upload_limits":20
                }
            })
        else:
            super().__init__({
                "free": {
                    "name": "Free",
                    "job_postings_limit": 3,
                    "is_lifetime_cap": True,
                    "resume_access_limit": 5,
                },
                "startup": {
                    "name": "Startup",
                    "job_postings_limit": 5,
                    "is_lifetime_cap": False,
                    "resume_access_limit": 20,
                },
                "msme": {
                    "name": "MSME",
                    "job_postings_limit": 15,
                    "is_lifetime_cap": False,
                    "resume_access_limit": 50,
                },
                "enterprise": {
                    "name": "Enterprise",
                    "job_postings_limit": 50,
                    "is_lifetime_cap": False,
                    "resume_access_limit": 100,
                }
            })

    def get_limits(self, tier: str, db: Session) -> dict:
        tier_lower = (tier or "free").lower()
        # In DB, name is capitalized: 'Free', 'Sliver', 'Gold', 'Platinum', 'Startup', 'MSME', 'Enterprise'
        db_name = tier_lower.capitalize()
        if db_name == "Silver":
            db_name = "Sliver"
        elif db_name == "Msme":
            db_name = "MSME"

        try:
            from app.models.meta import MetaSubscriptionPlan
            plan = db.query(MetaSubscriptionPlan).filter(
                MetaSubscriptionPlan.role == self.role,
                MetaSubscriptionPlan.is_active == True,
                MetaSubscriptionPlan.name.ilike(db_name)
            ).first()
            
            if plan and plan.features:
                # Merge DB limits into a copy of defaults
                default_tier = "silver" if tier_lower == "sliver" else tier_lower
                limits = self.get(default_tier, self["free"]).copy()
                for key in limits:
                    if key in plan.features:
                        # Extract and cast type from DB features to match expected default type
                        val = plan.features[key]
                        if isinstance(limits[key], bool):
                            limits[key] = bool(val)
                        elif isinstance(limits[key], int):
                            limits[key] = int(val)
                        else:
                            limits[key] = val
                limits["name"] = plan.name
                return limits
        except Exception as e:
            logger.warning(f"Error loading subscription plan limits from DB for tier {tier}: {e}")
            
        default_tier = "silver" if tier_lower == "sliver" else tier_lower
        return self.get(default_tier, self["free"])


PLAN_LIMITS = DynamicPlanLimits("candidate")
POSTER_PLAN_LIMITS = DynamicPlanLimits("employer")
