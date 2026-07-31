import sys
import os
from uuid import UUID

# Ensure the app package is discoverable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.models.notification import Notification
from app.models.application import JobApplication
from app.tasks.notifications import get_candidate_action_url

def update_notification_urls():
    db = SessionLocal()
    try:
        # Find all notifications with action_url starting with /applications/
        # which corresponds to resume_view or other old candidate notifications.
        notifications = db.query(Notification).filter(
            Notification.action_url.like("/applications/%")
        ).all()
        
        print(f"Found {len(notifications)} notifications with old candidate URL format.")
        
        updated_count = 0
        for notification in notifications:
            old_url = notification.action_url
            # Extract application ID from URL (/applications/<uuid>)
            parts = old_url.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "applications":
                app_id_str = parts[1]
                try:
                    app_id = UUID(app_id_str)
                    # Lookup corresponding JobApplication to find status
                    app = db.query(JobApplication).filter(JobApplication.id == app_id).first()
                    if app:
                        new_url = get_candidate_action_url(app.status)
                    else:
                        # Fallback if application was deleted
                        new_url = "/applications-candidate?tab=applied"
                    
                    notification.action_url = new_url
                    updated_count += 1
                    print(f"Updated notification {notification.id}: {old_url} -> {new_url}")
                except ValueError:
                    print(f"Skipping notification {notification.id} due to invalid UUID: {app_id_str}")
        
        if updated_count > 0:
            db.commit()
            print(f"Successfully committed changes. Total updated: {updated_count} rows.")
        else:
            print("No notifications needed update.")
            
    except Exception as e:
        db.rollback()
        print(f"Error during migration: {str(e)}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    update_notification_urls()
