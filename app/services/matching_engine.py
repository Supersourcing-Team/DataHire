from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Dict, Any, List
import numpy as np

from app.models.job import JobPosting
from app.models.resume import Resume

class MatchingEngine:
    # Weight Distributions (out of 100)
    WEIGHT_SEMANTIC = 0.40
    WEIGHT_SKILLS = 0.30
    WEIGHT_EXPERIENCE = 0.20
    WEIGHT_FILTERS = 0.10

    def __init__(self, db: Session):
        self.db = db

    def calculate_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if vec1 is None or vec2 is None or len(vec1) == 0 or len(vec2) == 0:
            return 0.0
        if len(vec1) != len(vec2):
            return 0.0
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
            
        return float(dot_product / (norm_v1 * norm_v2))

    def evaluate_semantic_fit(self, job: JobPosting, resume: Resume) -> float:
        """
        Calculates Semantic Context & Fit Score (0-100 scale).
        Includes domain multiplier and seniority penalty.
        """
        if job.embedding is None or resume.overall_embedding is None:
            return 0.0
            
        # Base Cosine Similarity (-1 to 1) normalized to (0 to 100)
        base_similarity = self.calculate_cosine_similarity(job.embedding, resume.overall_embedding)
        base_score = max(0.0, (base_similarity + 1) / 2) * 100
        
        # Domain Multiplier: Boost score slightly if they belong to the same taxonomy domain
        if job.taxonomy_domain_id and resume.taxonomy_domain_id and (job.taxonomy_domain_id == resume.taxonomy_domain_id):
            base_score = min(100.0, base_score * 1.1) 
            
        return base_score

    def evaluate_skills_overlap(self, job: JobPosting, resume: Resume) -> Dict[str, Any]:
        """
        Calculates Hard Skills Overlap Score (0-100 scale).
        Returns the score, matched skills, and missing critical skills.
        """
        # Normalize job skills and preserve original casing in a lookup dictionary
        job_skills_raw = job.extracted_skills or []
        job_skills_lower = {}
        for s in job_skills_raw:
            if s and isinstance(s, str):
                cleaned = s.strip()
                if cleaned:
                    job_skills_lower[cleaned.lower()] = cleaned

        # Normalize resume skills
        resume_skills_raw = resume.extracted_skills or []
        resume_skills_lower = set()
        for s in resume_skills_raw:
            if s and isinstance(s, str):
                cleaned = s.strip()
                if cleaned:
                    resume_skills_lower.add(cleaned.lower())

        if not job_skills_lower:
            return {"score": 100.0, "matched": list(resume_skills_raw), "missing": []}

        matched_keys = set(job_skills_lower.keys()).intersection(resume_skills_lower)
        missing_keys = set(job_skills_lower.keys()).difference(resume_skills_lower)

        # Map back to original casing from the job posting
        matched_skills = [job_skills_lower[k] for k in matched_keys]
        missing_skills = [job_skills_lower[k] for k in missing_keys]

        score = (len(matched_skills) / len(job_skills_lower)) * 100

        return {
            "score": score,
            "matched": matched_skills,
            "missing": missing_skills
        }

    def evaluate_experience_match(self, job: JobPosting, resume: Resume) -> float:
        """
        Calculates Experience Match Score (0-100 scale).
        """
        req_exp = job.min_experience_years
        cand_exp = resume.total_experience_years
        
        if req_exp == 0:
            return 100.0
            
        if cand_exp >= req_exp:
            return 100.0
            
        # Partial score if candidate has less experience
        # e.g. required=4, candidate=3 -> 75% points
        return (cand_exp / req_exp) * 100

    def evaluate_logistics(self, job: JobPosting, resume: Resume) -> float:
        """
        Calculates Logistics & Filters Score (0-100 scale) based on candidate preferences.
        """
        candidate = resume.candidate
        if not candidate:
            return 100.0

        score_components = []

        # 1. Role Type Match
        if candidate.pref_role_type:
            roles = [r.strip().lower() for r in candidate.pref_role_type.split(",") if r.strip()]
            if roles:
                job_title_lower = job.title.lower() if job.title else ""
                match = any(role in job_title_lower for role in roles)
                score_components.append(100.0 if match else 0.0)

        # 2. Location Match
        if candidate.pref_locations:
            locations = [l.strip().lower() for l in candidate.pref_locations.split(",") if l.strip()]
            if locations:
                match = False
                # Check remote
                if "remote" in locations and job.work_mode and job.work_mode.name.lower() == "remote":
                    match = True
                else:
                    city_name = job.city.name.lower() if job.city and job.city.name else ""
                    state_name = job.state.name.lower() if job.state and job.state.name else ""
                    country_name = job.country.name.lower() if job.country and job.country.name else ""
                    
                    match = any(
                        loc in city_name or loc in state_name or loc in country_name
                        for loc in locations if loc != "remote"
                    )
                score_components.append(100.0 if match else 0.0)

        # 3. Salary Match
        if candidate.pref_min_salary is not None:
            if job.salary_max is not None:
                match = (job.salary_max >= candidate.pref_min_salary)
                score_components.append(100.0 if match else 0.0)
            elif job.salary_min is not None:
                match = (job.salary_min >= candidate.pref_min_salary)
                score_components.append(100.0 if match else 0.0)
            else:
                # Job has no salary specified
                score_components.append(100.0)

        if not score_components:
            return 100.0

        return sum(score_components) / len(score_components)

    def score_resume_for_job(self, resume_id: str, job_id: str) -> Dict[str, Any]:
        """
        The main engine function that scores a single resume against a job.
        """
        job = self.db.query(JobPosting).filter(JobPosting.id == job_id).first()
        resume = self.db.query(Resume).filter(Resume.id == resume_id).first()
        
        if not job or not resume:
            raise ValueError("Job or Resume not found.")

        return self.score_resume_object_for_job_object(resume, job)

    def score_resume_object_for_job_object(self, resume: Resume, job: JobPosting) -> Dict[str, Any]:
        """
        Calculates match score using pre-loaded Resume and JobPosting models
        without triggering database ID lookups.
        """
        # 1. Semantic Score
        semantic_score = self.evaluate_semantic_fit(job, resume)
        
        # 2. Skills Score
        skills_eval = self.evaluate_skills_overlap(job, resume)
        skills_score = skills_eval["score"]
        
        # 3. Experience Score
        experience_score = self.evaluate_experience_match(job, resume)
        
        # 4. Logistics Score
        logistics_score = self.evaluate_logistics(job, resume)
        
        # Weighted Final Score
        final_score = (
            (semantic_score * self.WEIGHT_SEMANTIC) +
            (skills_score * self.WEIGHT_SKILLS) +
            (experience_score * self.WEIGHT_EXPERIENCE) +
            (logistics_score * self.WEIGHT_FILTERS)
        )
        
        return {
            "resume_id": str(resume.id),
            "job_id": str(job.id),
            "final_score": round(final_score, 2),
            "breakdown": {
                "semantic": round(semantic_score, 2),
                "skills": round(skills_score, 2),
                "experience": round(experience_score, 2),
                "logistics": round(logistics_score, 2)
            },
            "insights": {
                "matched_skills": skills_eval["matched"],
                "missing_skills": skills_eval["missing"]
            }
        }

