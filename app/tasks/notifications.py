import json
import logging
from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.application import JobApplication
from app.models.notification import Notification, NotificationPreference
from app.services.sendgrid_service import SendGridService

logger = logging.getLogger(__name__)

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
    name="app.tasks.notifications.send_email_task"
)
def send_email_task(self, to_email: str, template_name_or_id: str, template_data: dict, subject: str) -> bool:
    """
    Asynchronously sends an email via SendGridService.
    Automatically retries on network failures or rate limits (e.g. 429) using exponential backoff.
    """
    import asyncio
    logger.info(f"Sending email to {to_email} with template/ID {template_name_or_id}")
    
    success = asyncio.run(
        SendGridService.send_mail_with_template(
            to_email=to_email,
            template_name_or_id=template_name_or_id,
            template_data=template_data,
            subject=subject
        )
    )
    if not success:
        logger.warning(f"Failed to send email to {to_email}, scheduling retry...")
        raise Exception(f"Failed to send email to {to_email}")
        
    return True


@celery_app.task(name="app.tasks.notifications.create_in_app_notification_task")
def create_in_app_notification_task(user_id: str, title: str, content: str, notification_type: str, action_url: str = None) -> bool:
    """
    Asynchronously creates an in-app notification in the database and
    publishes the event to Redis Pub/Sub for WebSocket push distribution.
    """
    db = SessionLocal()
    try:
        # Check user preference first (if preference exists and channel is disabled, skip)
        pref = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type
        ).first()
        
        if pref and not pref.in_app_enabled:
            logger.info(f"User {user_id} has disabled in-app notifications for type {notification_type}")
            return False

        # Create database notification record
        new_notification = Notification(
            user_id=user_id,
            title=title,
            content=content,
            notification_type=notification_type,
            action_url=action_url
        )
        db.add(new_notification)
        db.commit()
        db.refresh(new_notification)

        # Publish to Redis Pub/Sub
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL or "redis://localhost:6379")
            payload = {
                "id": str(new_notification.id),
                "user_id": str(user_id),
                "title": title,
                "content": content,
                "notification_type": notification_type,
                "action_url": action_url,
                "created_at": new_notification.created_at.isoformat()
            }
            r.publish("datahire_notifications", json.dumps(payload))
            logger.info(f"Notification published to Redis Pub/Sub for user {user_id}")
        except Exception as pub_err:
            logger.error(f"Failed to publish notification to Redis Pub/Sub: {str(pub_err)}")

        return True
    except Exception as e:
        logger.error(f"Failed to create in-app notification for user {user_id}: {str(e)}")
        return False
    finally:
        db.close()


def get_candidate_action_url(status: str) -> str:
    status_lower = status.strip().lower()
    mapping = {
        "applied": "applied",
        "under_review": "applied",
        "shortlisted": "shortlisted",
        "interviewing": "interview",
        "interviewed": "interview",
        "offered": "interview",
        "onhold": "onhold",
        "hired": "hired",
        "rejected": "rejected"
    }
    tab = mapping.get(status_lower, "applied")
    return f"/applications-candidate?tab={tab}"


def get_employer_action_url(job_id: str, status: str) -> str:
    status_lower = status.strip().lower()
    mapping = {
        "applied": "applied",
        "under_review": "applied",
        "shortlisted": "shortlisted",
        "interviewing": "interview",
        "interviewed": "interview",
        "offered": "interview",
        "onhold": "onhold",
        "hired": "hired",
        "rejected": "rejected"
    }
    tab = mapping.get(status_lower, "applied")
    if tab == "applied":
        return f"/hire-candidate?jobId={job_id}&tab=applied"
    else:
        return f"/hire-candidate?jobId={job_id}&tab={tab}&page=1"


@celery_app.task(name="app.tasks.notifications.send_application_creation_notifications_task")
def send_application_creation_notifications_task(application_id: str) -> bool:
    """
    Asynchronous task to handle downstream notifications after a job application is created.
    This task decouples notifications from the core apply transaction.
    """
    logger.info(f"Triggering application creation notifications for App ID: {application_id}")
    
    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter(JobApplication.id == application_id).first()
        if not application:
            logger.error(f"Application {application_id} not found in database.")
            return False
            
        candidate = application.candidate
        job = application.job
        
        # Determine candidate's user details
        candidate_user = candidate.user
        candidate_email = candidate_user.email
        candidate_name = candidate.full_name
        
        # 1. Trigger Async Email Notification
        email_data = {
            "name": candidate_name,
            "job_title": job.title,
            "company_name": job.company.name if job.company else "the Employer",
            "application_url": f"{settings.FRONTEND_URL}{get_candidate_action_url(application.status)}"
        }
        send_email_task.delay(
            to_email=candidate_email,
            template_name_or_id="emails/auto_apply_success.html",
            template_data=email_data,
            subject=f"Application Submitted: {job.title}"
        )
        
        # 2. Trigger Async In-App Notification
        create_in_app_notification_task.delay(
            user_id=str(candidate_user.id),
            title="Auto-Applied!",
            content=f"Successfully applied to {job.title}",
            notification_type="auto_apply_success",
            action_url=get_candidate_action_url(application.status)
        )
        
        # 3. AI Shortlisted Notification for Job Poster (Employer)
        if application.status == "shortlisted":
            if job.company:
                for emp in job.company.employers:
                    emp_user_id = str(emp.user_id)
                    emp_email = emp.user.email
                    
                    # Email
                    ai_email_data = {
                        "employer_name": emp.contact_person or emp_email,
                        "candidate_name": candidate_name,
                        "job_title": job.title,
                        "candidate_id": str(candidate.id),
                        "job_id": str(job.id),
                        "application_url": f"{settings.FRONTEND_URL}/job-posters/jobs/{job.id}/applicants/{candidate.id}"
                    }
                    send_email_task.delay(
                        to_email=emp_email,
                        template_name_or_id="emails/ai_shortlist.html",
                        template_data=ai_email_data,
                        subject=f"AI Shortlisted Candidate: {candidate_name}"
                    )
                    
                    # In-App
                    create_in_app_notification_task.delay(
                        user_id=emp_user_id,
                        title="AI Shortlisted Candidate",
                        content=f"Candidate {candidate_name} has been AI shortlisted for your job '{job.title}'.",
                        notification_type="ai_shortlist",
                        action_url=get_employer_action_url(str(job.id), "shortlisted")
                    )
        
        return True
    except Exception as e:
        logger.error(f"Failed to process notifications for Application {application_id}: {str(e)}")
        return False
    finally:
        db.close()


@celery_app.task(name="app.tasks.notifications.send_welcome_notification_task")
def send_welcome_notification_task(user_id: str) -> bool:
    """
    Sends a welcome email (Email-only).
    """
    db = SessionLocal()
    try:
        from app.models.user import User, UserRole
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found for welcome notification.")
            return False
            
        full_name = user.email
        if user.role == UserRole.CANDIDATE and user.candidate:
            full_name = user.candidate.full_name or user.email
        elif user.role == UserRole.EMPLOYER and user.employer:
            full_name = user.employer.contact_person or user.email

        # Send welcome email
        email_data = {
            "name": full_name,
            "dashboard_url": f"{settings.FRONTEND_URL}/dashboard"
        }
        send_email_task.delay(
            to_email=user.email,
            template_name_or_id="emails/welcome.html",
            template_data=email_data,
            subject="Welcome to DataHire"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send welcome notification for user {user_id}: {str(e)}")
        return False
    finally:
        db.close()


@celery_app.task(name="app.tasks.notifications.run_daily_notifications_job")
def run_daily_notifications_job() -> bool:
    """
    Runs once a day to check and trigger scheduled/cron-like notifications:
    1. Token Expiry (Access/Refresh session expiring in < 7 days)
    2. Saved Job Expiring (expires in < 3 days)
    3. Job Expiry (expires in < 3 days)
    4. Daily application summary for employers (Job Poster)
    """
    db = SessionLocal()
    try:
        from datetime import datetime, timezone, timedelta
        from app.models.user import User, UserRole
        from app.models.refresh_token import RefreshToken
        from app.models.saved_job import SavedJob
        from app.models.job import JobPosting, JobStatus
        from app.models.application import JobApplication
        from app.models.employer import Employer

        now = datetime.now(timezone.utc)
        three_days_from_now = now + timedelta(days=3)
        seven_days_from_now = now + timedelta(days=7)

        # 1. Token Expiry (Warn users whose refresh tokens will expire in less than 7 days)
        expiring_tokens = db.query(RefreshToken).filter(
            RefreshToken.expires_at > now,
            RefreshToken.expires_at <= seven_days_from_now
        ).all()
        notified_users = set()
        for token in expiring_tokens:
            if token.user_id not in notified_users:
                # Email
                send_email_task.delay(
                    to_email=token.user.email,
                    template_name_or_id="emails/token_expiry.html",
                    template_data={"name": token.user.email},
                    subject="Login Session Expiring Soon"
                )
                # In-App
                create_in_app_notification_task.delay(
                    user_id=str(token.user_id),
                    title="Session Expiring Soon",
                    content="Your login session is scheduled to expire in less than 7 days. Please log in again to extend it.",
                    notification_type="token_expiry",
                    action_url="/dashboard"
                )
                notified_users.add(token.user_id)

        # 2. Saved Job Expiring (expires in < 3 days)
        expiring_saved_jobs = db.query(SavedJob).join(JobPosting).filter(
            JobPosting.is_active == True,
            JobPosting.status == JobStatus.PUBLISHED,
            JobPosting.application_deadline > now,
            JobPosting.application_deadline <= three_days_from_now
        ).all()
        for saved in expiring_saved_jobs:
            candidate_user_id = saved.candidate.user_id
            expiry_str = saved.job.application_deadline.strftime('%Y-%m-%d')
            # Email
            send_email_task.delay(
                to_email=saved.candidate.user.email,
                template_name_or_id="emails/saved_job_expiring.html",
                template_data={"name": saved.candidate.full_name, "job_title": saved.job.title, "expiry_days": 3},
                subject="Saved Job Expiring Soon"
            )
            # In-App
            create_in_app_notification_task.delay(
                user_id=str(candidate_user_id),
                title="Saved Job Expiring",
                content=f"Your saved job '{saved.job.title}' is expiring soon on {expiry_str}.",
                notification_type="saved_job_expiring",
                action_url=f"/jobs/{saved.job_id}"
            )

        # 3. Job Expiry (active job posting expiring in < 3 days)
        expiring_jobs = db.query(JobPosting).filter(
            JobPosting.is_active == True,
            JobPosting.status == JobStatus.PUBLISHED,
            JobPosting.application_deadline > now,
            JobPosting.application_deadline <= three_days_from_now
        ).all()
        for job in expiring_jobs:
            if job.company:
                expiry_str = job.application_deadline.strftime('%Y-%m-%d')
                for emp in job.company.employers:
                    # Email
                    send_email_task.delay(
                        to_email=emp.user.email,
                        template_name_or_id="emails/job_expiry.html",
                        template_data={"job_title": job.title, "expiry_date": expiry_str},
                        subject="Job Posting Expiring Soon"
                    )
                    # In-App
                    create_in_app_notification_task.delay(
                        user_id=str(emp.user_id),
                        title="Job Posting Expiring Soon",
                        content=f"Your job posting '{job.title}' is scheduled to expire on {expiry_str}.",
                        notification_type="job_expiry",
                        action_url=f"/job-posters/jobs/{job.id}"
                    )

        # 4. Daily application summary for employers (Total jobs applied for on a per day basis)
        yesterday = now - timedelta(days=1)
        recent_apps = db.query(JobApplication).filter(
            JobApplication.created_at >= yesterday
        ).all()
        
        # Group applications by employer and job
        employer_job_app_counts = {}  # {(employer_user_id, job_id, job_title): count}
        for app in recent_apps:
            if app.job and app.job.company:
                for emp in app.job.company.employers:
                    key = (emp.user_id, app.job_id, app.job.title)
                    employer_job_app_counts[key] = employer_job_app_counts.get(key, 0) + 1
                    
        for (user_id, job_id, job_title), count in employer_job_app_counts.items():
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                # Email
                send_email_task.delay(
                    to_email=user.email,
                    template_name_or_id="emails/employer_daily_summary.html",
                    template_data={"total_app_count": count},
                    subject="Daily Application Summary Report"
                )
                # In-App
                create_in_app_notification_task.delay(
                    user_id=str(user_id),
                    title="Daily Application Summary",
                    content=f"You received {count} new candidate application(s) today for your job '{job_title}'.",
                    notification_type="employer_daily_summary",
                    action_url=get_employer_action_url(str(job_id), "applied")
                )

        return True
    except Exception as e:
        logger.error(f"Failed to run daily notifications job: {str(e)}")
        return False
    finally:
        db.close()

