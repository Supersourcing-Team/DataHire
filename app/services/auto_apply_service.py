import logging
from sqlalchemy.orm import Session, joinedload
from app.models.candidate import Candidate, CandidateSkippedJob
from app.models.job import JobPosting
from app.models.application import JobApplication
from app.models.resume import Resume
from app.services.matching_engine import MatchingEngine

logger = logging.getLogger(__name__)

def execute_auto_apply_for_all(db: Session) -> dict:
    """
    Executes the auto-apply process for all active candidates in the database.
    Checks plan daily limits, monthly credits, preferences, and applies to top matching jobs.
    Returns summary statistics of the execution.
    """
    # Import these from job_seeker api to avoid circular dependencies and code duplication
    from app.api.v1.job_seeker import PLAN_LIMITS, check_and_reset_candidate_credits
    
    candidates = db.query(Candidate).all()
    stats = {
        "processed_candidates": 0,
        "applied_candidates": 0,
        "total_applications_created": 0,
        "errors": []
    }
    
    for candidate in candidates:
        if candidate.is_auto_apply_cancelled:
            continue

        # Check if candidate has preferences set
        has_preferences = bool(
            candidate.pref_role_type or 
            candidate.pref_locations or 
            candidate.pref_min_salary is not None
        )
        if not has_preferences:
            continue
            
        stats["processed_candidates"] += 1
        
        try:
            # Check and reset credits
            check_and_reset_candidate_credits(candidate, db)
            
            tier = candidate.plan_tier or "free"
            limits = PLAN_LIMITS.get(tier, PLAN_LIMITS["free"])
            
            # Check remaining daily and monthly credits
            remaining_daily = limits["daily_apply_limit"] - candidate.daily_apply_credits_used
            remaining_monthly = (limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used) // 2
            max_to_apply = min(remaining_daily, remaining_monthly)
            
            if max_to_apply <= 0:
                logger.info(f"Candidate {candidate.id} has no apply credits remaining for today.")
                continue
                
            # Verify primary resume
            primary_resume = db.query(Resume).filter(
                Resume.candidate_id == candidate.id,
                Resume.is_primary == True
            ).first()
            if not primary_resume:
                logger.info(f"Candidate {candidate.id} has no primary resume set.")
                continue
                
            # Query all active job postings
            query = (
                db.query(JobPosting)
                .options(joinedload(JobPosting.company))
                .filter(JobPosting.is_active == True)
            )
            
            # Exclude already applied
            applied_job_ids = db.query(JobApplication.job_id).filter(
                JobApplication.candidate_id == candidate.id
            ).all()
            applied_ids = [r[0] for r in applied_job_ids]
            if applied_ids:
                query = query.filter(JobPosting.id.not_in(applied_ids))
                
            # Exclude skipped
            skipped_job_ids = db.query(CandidateSkippedJob.job_id).filter(
                CandidateSkippedJob.candidate_id == candidate.id
            ).all()
            skipped_ids = [r[0] for r in skipped_job_ids]
            if skipped_ids:
                query = query.filter(JobPosting.id.not_in(skipped_ids))
                
            jobs = query.all()
            
            matching_service = MatchingEngine(db)
            scored_jobs = []
            
            pref_roles = [r.strip().lower() for r in candidate.pref_role_type.split(",") if r.strip()] if candidate.pref_role_type else []
            pref_locs = [l.strip().lower() for l in candidate.pref_locations.split(",") if l.strip()] if candidate.pref_locations else []
            
            for job in jobs:
                # Check role type match
                if pref_roles:
                    job_title = job.title.lower() if job.title else ""
                    if not any(role in job_title for role in pref_roles):
                        continue
                        
                # Check location match
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
                        
                # Check salary match
                if candidate.pref_min_salary is not None:
                    if job.salary_max is not None and job.salary_max < candidate.pref_min_salary:
                        continue
                    if job.salary_max is None and job.salary_min is not None and job.salary_min < candidate.pref_min_salary:
                        continue
                        
                # Calculate AI score
                ai_score = 0
                if primary_resume.overall_embedding is not None:
                    try:
                        score_details = matching_service.score_resume_for_job(primary_resume.id, job.id)
                        ai_score = int(score_details["final_score"])
                    except Exception:
                        ai_score = 0
                        
                scored_jobs.append((job, ai_score))
                
            if not scored_jobs:
                continue
                
            scored_jobs.sort(key=lambda x: x[1], reverse=True)
            top_matches = scored_jobs[:max_to_apply]
            
            apps_created = 0
            for job, ai_score in top_matches:
                # Determine status: "shortlisted" if ai_score matches or exceeds job's threshold (or default 70)
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
                apps_created += 1
                
            if apps_created > 0:
                db.add(candidate)
                db.commit()
                stats["applied_candidates"] += 1
                stats["total_applications_created"] += apps_created
                logger.info(f"Auto-applied {apps_created} jobs for Candidate {candidate.id}")
                
        except Exception as e:
            db.rollback()
            error_msg = f"Failed to execute auto-apply for Candidate {candidate.id}: {str(e)}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)
            
    return stats
