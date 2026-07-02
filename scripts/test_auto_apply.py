import os
import sys

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure Celery in eager mode (tasks run synchronously locally without a running worker/broker)
from app.core.celery_app import celery_app
celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True
)

from app.db.session import SessionLocal
from app.models.candidate import Candidate
from app.tasks.auto_apply import dispatch_auto_apply_all_task

def run_test():
    print("Running verification test for Auto Apply background tasks (Eager Mode)...")
    db = SessionLocal()
    try:
        # Check active candidates with preferences
        candidates = db.query(Candidate).all()
        eligible_count = 0
        for candidate in candidates:
            has_preferences = bool(
                candidate.pref_role_type or 
                candidate.pref_locations or 
                candidate.pref_min_salary is not None
            )
            if has_preferences:
                eligible_count += 1
                print(f"Candidate: {candidate.full_name} (ID: {candidate.id}) is eligible for auto-apply.")

        print(f"Total eligible candidates: {eligible_count}")
        
        # Dispatch the task
        print("Dispatching auto-apply dispatcher task...")
        result = dispatch_auto_apply_all_task.apply()
        print("Dispatcher task completed.")
        print(f"Task result: {result.result}")
        print("Verification complete. All tasks executed successfully in Eager Mode.")
    except Exception as e:
        print(f"Verification test failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_test()
