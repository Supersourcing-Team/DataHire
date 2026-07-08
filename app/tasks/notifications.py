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
            "application_url": f"http://localhost:3000/applications/{application_id}"
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
            action_url=f"/applications/{application_id}"
        )
        
        return True
    except Exception as e:
        logger.error(f"Failed to process notifications for Application {application_id}: {str(e)}")
        return False
    finally:
        db.close()
