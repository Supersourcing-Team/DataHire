import logging
from datetime import datetime, timezone
from sqlalchemy.orm import joinedload
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.candidate import Candidate, CandidateSkippedJob
from app.models.job import JobPosting
from app.models.application import JobApplication
from app.models.resume import Resume
from app.services.matching_engine import MatchingEngine
from app.services.plans_service import PLAN_LIMITS
from app.api.v1.job_seeker import check_and_reset_candidate_credits
from app.tasks.notifications import send_application_creation_notifications_task

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.auto_apply.execute_candidate_auto_apply_task")
def execute_candidate_auto_apply_task(candidate_id: str) -> bool:
    """
    Executes the auto-apply process for a single candidate.
    Calculates similarity and logistics in-memory using optimized queries.
    """
    logger.info(f"Starting auto-apply for candidate: {candidate_id}")
    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found.")
            return False

        if candidate.is_auto_apply_cancelled:
            logger.info(f"Candidate {candidate_id} has cancelled auto-apply.")
            return False

        # Verify candidate preferences (handling literal "None" strings)
        pref_role_str = candidate.pref_role_type
        if pref_role_str and pref_role_str.strip().lower() in ("none", "null", ""):
            pref_role_str = None
            
        pref_loc_str = candidate.pref_locations
        if pref_loc_str and pref_loc_str.strip().lower() in ("none", "null", ""):
            pref_loc_str = None

        has_preferences = bool(
            pref_role_str or 
            pref_loc_str or 
            candidate.pref_min_salary is not None
        )
        if not has_preferences:
            logger.info(f"Candidate {candidate_id} has no preferences set.")
            return False

        # Check and reset candidate credits
        check_and_reset_candidate_credits(candidate, db)

        tier = candidate.plan_tier or "free"
        limits = PLAN_LIMITS.get_limits(tier, db)

        # Check remaining daily and monthly credits
        remaining_daily = limits["daily_apply_limit"] - candidate.daily_apply_credits_used
        remaining_monthly = (limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used) // 2
        max_to_apply = min(remaining_daily, remaining_monthly)

        if max_to_apply <= 0:
            logger.info(f"Candidate {candidate_id} has no apply credits remaining for today.")
            return False

        # Verify primary resume
        primary_resume = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.is_primary == True
        ).first()
        if not primary_resume:
            logger.info(f"Candidate {candidate_id} has no primary resume set.")
            return False

        # Cache/Pre-load all active jobs once for this candidate's execution context
        # (This avoids the N+1 queries by fetching active jobs in bulk)
        active_jobs = (
            db.query(JobPosting)
            .options(joinedload(JobPosting.company))
            .filter(JobPosting.is_active == True)
            .all()
        )
        if not active_jobs:
            logger.info("No active jobs available in the system.")
            return False

        # Fetch excluded jobs (already applied or skipped)
        applied_job_ids = {
            r[0] for r in db.query(JobApplication.job_id).filter(
                JobApplication.candidate_id == candidate.id
            ).all()
        }
        skipped_job_ids = {
            r[0] for r in db.query(CandidateSkippedJob.job_id).filter(
                CandidateSkippedJob.candidate_id == candidate.id
            ).all()
        }

        # Filter jobs in-memory
        pref_roles = [r.strip().lower() for r in pref_role_str.split(",") if r.strip()] if pref_role_str else []
        pref_locs = [l.strip().lower() for l in pref_loc_str.split(",") if l.strip()] if pref_loc_str else []

        matching_service = MatchingEngine(db)
        scored_jobs = []

        for job in active_jobs:
            if job.id in applied_job_ids or job.id in skipped_job_ids:
                continue

            # Role Type check
            if pref_roles:
                job_title = job.title.lower() if job.title else ""
                if not any(role in job_title for role in pref_roles):
                    logger.debug(f"Candidate {candidate_id} task: skipping job {job.id} ({job.title}) - role mismatch.")
                    continue

            # Location check
            if pref_locs:
                match_loc = False
                if "remote" in pref_locs and job.work_mode and job.work_mode.name.lower() == "remote":
                    match_loc = True
                else:
                    city_name = job.city.name.lower() if job.city and job.city.name else ""
                    state_name = job.state.name.lower() if job.state and job.state.name else ""
                    country_name = job.country.name.lower() if job.country and job.country.name else ""
                    if any(loc in city_name or loc in state_name or loc in country_name for loc in pref_locs if loc != "remote"):
                        match_loc = True
                if not match_loc:
                    logger.debug(f"Candidate {candidate_id} task: skipping job {job.id} ({job.title}) - location mismatch.")
                    continue

            # Salary check
            if candidate.pref_min_salary is not None:
                if job.salary_max is not None and job.salary_max < candidate.pref_min_salary:
                    logger.debug(f"Candidate {candidate_id} task: skipping job {job.id} ({job.title}) - max salary {job.salary_max} < pref {candidate.pref_min_salary}.")
                    continue
                if job.salary_max is None and job.salary_min is not None and job.salary_min < candidate.pref_min_salary:
                    logger.debug(f"Candidate {candidate_id} task: skipping job {job.id} ({job.title}) - min salary {job.salary_min} < pref {candidate.pref_min_salary}.")
                    continue

            # Calculate score (using preloaded objects to avoid DB queries inside the loop!)
            ai_score = 0
            if primary_resume.overall_embedding is not None:
                try:
                    score_details = matching_service.score_resume_object_for_job_object(primary_resume, job)
                    ai_score = int(score_details["final_score"])
                    logger.debug(f"Candidate {candidate_id} task: scored job {job.id} ({job.title}) - AI Score: {ai_score}")
                except Exception as ex:
                    logger.warning(f"Error scoring resume {primary_resume.id} for job {job.id}: {ex}")
                    ai_score = 0
            else:
                logger.warning(f"Primary resume {primary_resume.id} for candidate {candidate_id} is missing overall_embedding. Scoring as 0.")

            scored_jobs.append((job, ai_score))

        if not scored_jobs:
            logger.info(f"No matching jobs found for candidate: {candidate_id}")
            return False

        # Sort by match score descending and take the top matches
        scored_jobs.sort(key=lambda x: x[1], reverse=True)
        top_matches = scored_jobs[:max_to_apply]

        created_app_ids = []
        for job, ai_score in top_matches:
            # Determine application status
            threshold = job.ai_score_threshold if (job.ai_score_threshold and job.ai_score_threshold > 0) else 70
            app_status = "shortlisted" if ai_score >= threshold else "applied"

            new_app = JobApplication(
                candidate_id=candidate.id,
                job_id=job.id,
                status=app_status,
                apply_mode="auto-apply",
                resume_id=primary_resume.id
            )

            # Deduct credits
            candidate.daily_apply_credits_used += 1
            candidate.monthly_ai_credits_used += 2

            db.add(new_app)
            db.flush()  # Generate app ID
            created_app_ids.append(str(new_app.id))

        if created_app_ids:
            db.add(candidate)
            db.commit()
            
            # Trigger decoupled notifications AFTER the transaction has successfully committed
            for app_id in created_app_ids:
                send_application_creation_notifications_task.delay(app_id)
                
            logger.info(f"Successfully auto-applied to {len(created_app_ids)} jobs for candidate {candidate.id}")
            return True

        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Error running auto-apply for candidate {candidate_id}: {str(e)}")
        return False
    finally:
        db.close()

@celery_app.task(name="app.tasks.auto_apply.dispatch_auto_apply_all_task")
def dispatch_auto_apply_all_task() -> dict:
    """
    Orchestrator task that retrieves all candidate IDs with configured preferences
    and schedules individual auto-apply tasks.
    """
    logger.info("Starting global auto-apply dispatcher task...")
    db = SessionLocal()
    try:
        # Preload all active candidate subscription plans from the DB to avoid N+1 query problem
        from app.models.meta import MetaSubscriptionPlan
        plans = db.query(MetaSubscriptionPlan).filter(
            MetaSubscriptionPlan.role == "candidate",
            MetaSubscriptionPlan.is_active == True
        ).all()
        plans_cache = {p.name.lower(): p.features for p in plans if p.features}
        logger.info(f"Preloaded {len(plans_cache)} candidate subscription plan configs from database.")

        # Fetch candidates
        candidates = db.query(Candidate).all()
        logger.info(f"Fetched {len(candidates)} total candidates to evaluate for auto-apply eligibility.")
        
        candidate_ids = []
        for candidate in candidates:
            # Determine limits in-memory using preloaded plans
            tier_lower = (candidate.plan_tier or "free").lower()
            db_name = "sliver" if tier_lower == "silver" else tier_lower
            
            # Get default limits
            limits = PLAN_LIMITS.get(db_name, PLAN_LIMITS["free"]).copy()
            
            # Overlay DB features if available
            db_features = plans_cache.get(db_name)
            if db_features:
                for key in limits:
                    if key in db_features:
                        val = db_features[key]
                        if isinstance(limits[key], bool):
                            limits[key] = bool(val)
                        elif isinstance(limits[key], int):
                            limits[key] = int(val)
                        else:
                            limits[key] = val
                            
            if limits.get("daily_apply_limit", 0) <= 0:
                logger.debug(f"Candidate {candidate.id} excluded: daily apply limit is 0 for tier {candidate.plan_tier}.")
                continue

            pref_role_str = candidate.pref_role_type
            if pref_role_str and pref_role_str.strip().lower() in ("none", "null", ""):
                pref_role_str = None
                
            pref_loc_str = candidate.pref_locations
            if pref_loc_str and pref_loc_str.strip().lower() in ("none", "null", ""):
                pref_loc_str = None

            has_preferences = bool(
                pref_role_str or 
                pref_loc_str or 
                candidate.pref_min_salary is not None
            )
            if not has_preferences:
                logger.debug(f"Candidate {candidate.id} excluded: no preferences set (role: {candidate.pref_role_type}, location: {candidate.pref_locations}, salary: {candidate.pref_min_salary}).")
                continue

            # If candidate auto-apply is cancelled, we skip them from dispatching to avoid unnecessary celery tasks
            if candidate.is_auto_apply_cancelled:
                logger.debug(f"Candidate {candidate.id} excluded: auto-apply is cancelled.")
                continue

            candidate_ids.append(str(candidate.id))

        logger.info(f"Found {len(candidate_ids)} candidates eligible for auto-apply. Spawning tasks.")

        # Spawn a Celery task for each candidate
        for c_id in candidate_ids:
            logger.info(f"Dispatching auto-apply task for Candidate {c_id}")
            execute_candidate_auto_apply_task.delay(c_id)

        return {
            "dispatched_count": len(candidate_ids),
            "candidate_ids": candidate_ids
        }
    except Exception as e:
        logger.error(f"Failed to dispatch auto-apply tasks: {str(e)}")
        return {"error": str(e)}
    finally:
        db.close()
