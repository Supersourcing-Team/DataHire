import os
import sys

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from app.core.dependencies import get_current_active_user
from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.models.candidate import Candidate
from app.models.employer import Employer
from app.models.company import Company

def run_test():
    print("Verifying Candidate & Employer Profile Management APIs...")
    db = SessionLocal()
    try:
        # --- Part 1: Candidate Profile Test ---
        candidate = db.query(Candidate).first()
        if not candidate:
            print("No candidates found in database. Skipping candidate test.")
        else:
            cand_user = db.query(User).filter(User.id == candidate.user_id).first()
            if cand_user:
                # Force user role to CANDIDATE
                cand_user.role = UserRole.CANDIDATE
                db.add(cand_user)
                db.commit()

                print(f"Testing Candidate: {candidate.full_name}")
                app.dependency_overrides[get_current_active_user] = lambda: cand_user
                client = TestClient(app)

                # GET profile
                res = client.get("/api/v1/job-seeker/profile")
                assert res.status_code == 200, f"GET Candidate Profile failed: {res.text}"
                data = res.json()
                print("GET Candidate Profile Success:")
                print(f"  Name: {data['full_name']}, Email: {data['email']}, Phone: {data['phone']}")

                # PUT profile update
                update_payload = {
                    "phone": "999-888-7777",
                    "pref_locations": "San Francisco, Seattle"
                }
                res = client.put("/api/v1/job-seeker/profile", json=update_payload)
                assert res.status_code == 200, f"PUT Candidate Profile failed: {res.text}"
                updated_data = res.json()
                assert updated_data["phone"] == "999-888-7777"
                assert updated_data["pref_locations"] == "San Francisco, Seattle"
                print("PUT Candidate Profile Success.")
                
                app.dependency_overrides.clear()

        # --- Part 2: Employer Profile Test ---
        # Fetch or create an employer
        employer = db.query(Employer).first()
        if not employer:
            print("No employer found in database. Creating a mock employer...")
            # We need a user to attach to
            test_user = db.query(User).filter(User.email == "testemployer@datahire.com").first()
            if not test_user:
                test_user = User(
                    email="testemployer@datahire.com",
                    hashed_password="hashed_pw_here",
                    role=UserRole.EMPLOYER,
                    is_active=True
                )
                db.add(test_user)
                db.flush()
            
            employer = Employer(
                user_id=test_user.id,
                contact_person="Test Employer Person",
                phone="123-456-7890"
            )
            db.add(employer)
            db.commit()
            db.refresh(employer)

        emp_user = db.query(User).filter(User.id == employer.user_id).first()
        emp_user.role = UserRole.EMPLOYER
        db.add(emp_user)
        db.commit()

        print(f"Testing Employer: {employer.contact_person}")
        app.dependency_overrides[get_current_active_user] = lambda: emp_user
        client = TestClient(app)

        # GET profile
        res = client.get("/api/v1/employers/profile")
        assert res.status_code == 200, f"GET Employer Profile failed: {res.text}"
        data = res.json()
        print("GET Employer Profile Success:")
        print(f"  Contact Person: {data['contact_person']}, Email: {data['email']}, Phone: {data['phone']}")

        # PUT profile update (including creating/updating associated company)
        update_payload = {
            "contact_person": "Jane Doe Updated",
            "phone": "555-555-1234",
            "company_name": "Globex Corp",
            "company_website": "https://globex.com",
            "company_description": "We build awesome things"
        }
        res = client.put("/api/v1/employers/profile", json=update_payload)
        assert res.status_code == 200, f"PUT Employer Profile failed: {res.text}"
        updated_data = res.json()
        
        assert updated_data["contact_person"] == "Jane Doe Updated"
        assert updated_data["phone"] == "555-555-1234"
        assert updated_data["company"]["name"] == "Globex Corp"
        assert updated_data["company"]["website"] == "https://globex.com/"
        assert updated_data["company"]["description"] == "We build awesome things"
        print("PUT Employer Profile Success.")

        # Clean up dependency overrides
        app.dependency_overrides.clear()
        print("\nSUCCESS: Profile management APIs verified successfully!")

    except Exception as e:
        print(f"Profile API verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_test()
