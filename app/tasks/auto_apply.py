import logging
from datetime import datetime, timezone
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.candidate import Candidate, CandidateSkippedJob
from app.models.job import JobPosting
from app.models.application import JobApplication
from app.models.resume import Resume
from app.services.matching_engine import MatchingEngine
from app.api.v1.job_seeker import PLAN_LIMITS, check_and_reset_candidate_credits
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

        # Verify candidate preferences
        has_preferences = bool(
            candidate.pref_role_type or 
            candidate.pref_locations or 
            candidate.pref_min_salary is not None
        )
        if not has_preferences:
            logger.info(f"Candidate {candidate_id} has no preferences set.")
            return False

        # Check and reset candidate credits
        check_and_reset_candidate_credits(candidate, db)

        tier = candidate.plan_tier or "free"
        limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])

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
        pref_roles = [r.strip().lower() for r in candidate.pref_role_type.split(",") if r.strip()] if candidate.pref_role_type else []
        pref_locs = [l.strip().lower() for l in candidate.pref_locations.split(",") if l.strip()] if candidate.pref_locations else []

        matching_service = MatchingEngine(db)
        scored_jobs = []

        for job in active_jobs:
            if job.id in applied_job_ids or job.id in skipped_job_ids:
                continue

            # Role Type check
            if pref_roles:
                job_title = job.title.lower() if job.title else ""
                if not any(role in job_title for role in pref_roles):
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
                    continue

            # Salary check
            if candidate.pref_min_salary is not None:
                if job.salary_max is not None and job.salary_max < candidate.pref_min_salary:
                    continue
                if job.salary_max is None and job.salary_min is not None and job.salary_min < candidate.pref_min_salary:
                    continue

            # Calculate score (using preloaded objects to avoid DB queries inside the loop!)
            ai_score = 0
            if primary_resume.overall_embedding is not None:
                try:
                    score_details = matching_service.score_resume_object_for_job_object(primary_resume, job)
                    ai_score = int(score_details["final_score"])
                except Exception as ex:
                    logger.warning(f"Error scoring resume {primary_resume.id} for job {job.id}: {ex}")
                    ai_score = 0

            scored_jobs.append((job, ai_score))

        if not scored_jobs:
            logger.info(f"No matching jobs found for candidate: {candidate_id}")
            return False

        # Sort by match score descending and take the top matches
        scored_jobs.sort(key=lambda x: x[1], reverse=True)
        top_matches = scored_jobs[:max_to_apply]

        apps_created = 0
        for job, ai_score in top_matches:
            # Determine application status
            threshold = job.ai_score_threshold if (job.ai_score_threshold and job.ai_score_threshold > 0) else 70
            app_status = "shortlisted" if ai_score >= threshold else "applied"

            new_app = JobApplication(
                candidate_id=candidate.id,
                job_id=job.id,
                status=app_status,
                apply_mode="auto-apply"
            )

            # Deduct credits
            candidate.daily_apply_credits_used += 1
            candidate.monthly_ai_credits_used += 2

            db.add(new_app)
            db.flush()  # Generate app ID

            # Trigger decoupled notification
            send_application_creation_notifications_task.delay(str(new_app.id))
            apps_created += 1

        if apps_created > 0:
            db.add(candidate)
            db.commit()
            logger.info(f"Successfully auto-applied to {apps_created} jobs for candidate {candidate.id}")
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
        # Fetch candidates who have preferences configured (filter at database level)
        candidates = db.query(Candidate.id).filter(
            or_(
                Candidate.pref_role_type.isnot(None),
                Candidate.pref_locations.isnot(None),
                Candidate.pref_min_salary.isnot(None)
            )
        ).all()
        candidate_ids = [str(r[0]) for r in candidates]

        logger.info(f"Found {len(candidate_ids)} candidates eligible for auto-apply.")

        # Spawn a Celery task for each candidate
        for c_id in candidate_ids:
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
