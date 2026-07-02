import os
import sys
from datetime import datetime, timezone, timedelta

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from app.core.dependencies import get_current_active_user
from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.models.candidate import Candidate
from app.models.application import JobApplication
from app.models.job import JobPosting

def run_test():
    print("Verifying Credits Score & Streak API...")
    db = SessionLocal()
    try:
        # 1. Fetch or create a test candidate
        candidate = db.query(Candidate).first()
        if not candidate:
            print("No candidates found in the database. Exiting test.")
            return
            
        user = db.query(User).filter(User.id == candidate.user_id).first()
        if not user:
            print("Candidate's associated User not found. Exiting test.")
            return

        # Ensure user role is CANDIDATE
        user.role = UserRole.CANDIDATE
        db.add(user)
        db.commit()

        # Get one active job posting to associate with mock applications
        job = db.query(JobPosting).filter(JobPosting.is_active == True).first()
        if not job:
            print("No active job postings found. Exiting test.")
            return

        print(f"Testing with candidate: {candidate.full_name} (User: {user.email})")

        # 2. Setup mock applications to establish a streak
        # Clean up any existing auto-apply applications to start fresh
        db.query(JobApplication).filter(
            JobApplication.candidate_id == candidate.id,
            JobApplication.apply_mode == 'auto-apply'
        ).delete()
        db.commit()

        # Insert auto-apply applications for the last 3 days (today, yesterday, 2 days ago)
        now = datetime.now(timezone.utc)
        dates = [
            now,
            now - timedelta(days=1),
            now - timedelta(days=2)
        ]
        
        for index, d in enumerate(dates):
            # Create a mock job posting for each if they are unique
            # (To avoid unique constraint on candidate_id and job_id)
            mock_job = JobPosting(
                company_id=job.company_id,
                title=f"Mock Job {index}",
                is_active=True
            )
            db.add(mock_job)
            db.flush()
            
            app_record = JobApplication(
                candidate_id=candidate.id,
                job_id=mock_job.id,
                apply_mode="auto-apply",
                status="applied",
                created_at=d
            )
            db.add(app_record)
        db.commit()
        print("Inserted mock applications for a 3-day streak.")

        # 3. Call endpoint using TestClient and dependency override
        app.dependency_overrides[get_current_active_user] = lambda: user
        
        client = TestClient(app)
        response = client.get("/api/v1/job-seeker/dashboard/credits-score")
        
        # Clean up dependency override
        app.dependency_overrides.clear()
        
        # Clean up test database additions
        db.query(JobApplication).filter(
            JobApplication.candidate_id == candidate.id,
            JobApplication.apply_mode == 'auto-apply'
        ).delete()
        db.commit()

        print("Cleaned up mock applications.")

        # 4. Check results
        if response.status_code != 200:
            print(f"FAIL: Endpoint returned status code {response.status_code}")
            print(response.json())
            sys.exit(1)
            
        data = response.json()
        print("\n--- API Response Data ---")
        print(f"Plan Name: {data['plan_name']}")
        print(f"Current Streak: {data['current_streak']} Days")
        print(f"Running Week Status:")
        for day in data['running_week']:
            print(f"  {day['day']}: {'Applied' if day['applied'] else 'No auto-apply'}")
        print(f"Daily Limits: {data['daily_apply_credits_used']} / {data['daily_apply_credits_limit']}")
        print(f"Monthly Reset Date: {data['monthly_reset_date']}")
        print("-------------------------")

        assert data['current_streak'] == 3, f"Expected streak to be 3, got {data['current_streak']}"
        print("\nSUCCESS: Credits Score & Streak API verified successfully!")
        
    except Exception as e:
        print(f"Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_test()
