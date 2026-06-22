import os
import sys

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.services.auto_apply_service import execute_auto_apply_for_all

def main():
    print("Starting automated Auto Apply cron job...")
    db = SessionLocal()
    try:
        stats = execute_auto_apply_for_all(db)
        print("\n--- Auto Apply Execution Stats ---")
        print(f"Candidates processed: {stats['processed_candidates']}")
        print(f"Candidates applied: {stats['applied_candidates']}")
        print(f"Total applications created: {stats['total_applications_created']}")
        if stats["errors"]:
            print(f"Errors occurred: {len(stats['errors'])}")
            for err in stats["errors"]:
                print(f" - {err}")
        print("---------------------------------")
    except Exception as e:
        print(f"Fatal error during auto-apply cron job: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
