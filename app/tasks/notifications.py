import logging
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.application import JobApplication

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.notifications.send_application_creation_notifications_task")
def send_application_creation_notifications_task(application_id: str) -> bool:
    """
    Asynchronous task to handle downstream notifications after a job application is created.
    This task decouples notifications from the core apply transaction, avoiding timeouts
    and allowing easy plug-in of email and in-app notification services.
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
        
        # 1. TODO: MILESTONE - EMAIL NOTIFICATION
        # Retrieve candidate and employer emails.
        # Format templates (e.g. "You have automatically applied to [Job Title]")
        # Send via email service: app.services.email_service.send_email(...)
        logger.info(f"[Stub] Sending notification email to candidate {candidate.full_name} ({candidate.user.email}) for job {job.title}")
        
        # 2. TODO: MILESTONE - IN-APP NOTIFICATION CENTRE
        # Create a database record in a future `Notification` table:
        # notification = Notification(user_id=candidate.user_id, title="Auto-Applied!", content=f"Successfully applied to {job.title}")
        # db.add(notification)
        # db.commit()
        # Optionally trigger a WebSocket notification push to active UI clients
        logger.info(f"[Stub] Pushing notification to Candidate App Inbox (User ID: {candidate.user_id})")
        
        return True
    except Exception as e:
        logger.error(f"Failed to process notifications for Application {application_id}: {str(e)}")
        return False
    finally:
        db.close()
