import os
import sys

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.tasks.auto_apply import dispatch_auto_apply_all_task

def main():
    print("Starting automated Auto Apply cron job dispatcher...")
    try:
        # Trigger dispatcher Celery task
        result = dispatch_auto_apply_all_task.delay()
        print(f"Successfully enqueued global auto-apply dispatcher task (ID: {result.id}).")
        print("Celery workers will handle the candidate matches and application creation concurrently.")
    except Exception as e:
        print(f"Fatal error during auto-apply cron job dispatch: {e}")

if __name__ == "__main__":
    main()
