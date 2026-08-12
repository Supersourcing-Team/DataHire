from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Dict, Any, List
import numpy as np
import re
import logging

logger = logging.getLogger(__name__)


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
        self._skill_groups = None
        self._canonical_to_aliases = None
        self._job_role_aliases = None

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()

    def _load_taxonomy_skills(self):
        if self._skill_groups is not None:
            return
            
        from app.models.taxonomy import TaxonomySkill
        try:
            tax_skills = self.db.query(TaxonomySkill).filter(TaxonomySkill.is_active == True).all()
            groups = {}
            canonical_map = {}
            
            for ts in tax_skills:
                canonical = ts.name.lower().strip()
                norm_canonical = self._normalize_text(canonical)
                
                aliases_set = {norm_canonical}
                if ts.slug:
                    norm_slug = self._normalize_text(ts.slug)
                    if norm_slug:
                        aliases_set.add(norm_slug)
                if ts.aliases:
                    for alias in ts.aliases:
                        if alias and isinstance(alias, str):
                            norm_alias = self._normalize_text(alias)
                            if norm_alias:
                                aliases_set.add(norm_alias)
                                
                for variant in aliases_set:
                    groups[variant] = canonical
                    
                if canonical not in canonical_map:
                    canonical_map[canonical] = list(aliases_set)
                else:
                    canonical_map[canonical] = list(set(canonical_map[canonical]).union(aliases_set))
                    
            self._skill_groups = groups
            self._canonical_to_aliases = canonical_map
        except Exception as e:
            logger.error(f"Error loading taxonomy skills: {e}")
            self._skill_groups = {}
            self._canonical_to_aliases = {}

    def _get_job_role_aliases(self) -> Dict[int, List[str]]:
        if self._job_role_aliases is None:
            from app.models.taxonomy import TaxonomyJobRole
            try:
                tax_roles = self.db.query(TaxonomyJobRole).filter(TaxonomyJobRole.is_active == True).all()
                role_aliases = {}
                for tr in tax_roles:
                    aliases = [tr.name.lower().strip()]
                    if tr.slug:
                        aliases.append(tr.slug.lower().strip())
                    if tr.aliases:
                        for alias in tr.aliases:
                            if alias and isinstance(alias, str):
                                aliases.append(alias.lower().strip())
                    role_aliases[tr.id] = list(set(aliases))
                self._job_role_aliases = role_aliases
            except Exception as e:
                logger.error(f"Error loading taxonomy job roles: {e}")
                self._job_role_aliases = {}
        return self._job_role_aliases

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
            
        # Calibrated Cosine Similarity: Scale similarity in range [0.70, 0.85] to [0, 100]
        base_similarity = self.calculate_cosine_similarity(job.embedding, resume.overall_embedding)
        if base_similarity < 0.70:
            base_score = 0.0
        elif base_similarity > 0.85:
            base_score = 100.0
        else:
            base_score = ((base_similarity - 0.70) / (0.85 - 0.70)) * 100
        
        # Domain Multiplier: Boost score slightly if they belong to the same taxonomy domain
        if job.taxonomy_domain_id and resume.taxonomy_domain_id and (job.taxonomy_domain_id == resume.taxonomy_domain_id):
            base_score = min(100.0, base_score * 1.1) 
            
        return base_score

    def evaluate_skills_overlap(self, job: JobPosting, resume: Resume) -> Dict[str, Any]:
        """
        Calculates Hard Skills Overlap Score (0-100 scale).
        Uses multi-tier matching (exact, normalized, taxonomy alias mapping,
        token/word boundary matching, and fallback text search) for maximum accuracy.
        """
        job_skills_raw = job.resolved_skills
        job_skills_cleaned = [s.strip() for s in job_skills_raw if s and isinstance(s, str) and s.strip()]

        resume_skills_raw = resume.extracted_skills or []
        resume_skills_cleaned = [s.strip() for s in resume_skills_raw if s and isinstance(s, str) and s.strip()]

        # Always collect fallback text from resume sections and structured data
        parts = []
        if resume.structured_data:
            parts.append(str(resume.structured_data))
        if hasattr(resume, "sections") and resume.sections:
            for sec in resume.sections:
                content = getattr(sec, "optimized_content", None) or getattr(sec, "original_content", None)
                if content:
                    parts.append(str(content))
        fallback_text = " ".join(parts).lower()

        if not job_skills_cleaned:
            return {"score": 100.0, "matched": list(resume_skills_cleaned), "missing": []}

        # Lazy load taxonomy skills
        self._load_taxonomy_skills()
        skill_groups = self._skill_groups
        canonical_to_aliases = self._canonical_to_aliases

        matched_skills = []
        missing_skills = []

        resume_norm_list = [self._normalize_text(rs) for rs in resume_skills_cleaned]
        resume_norm_set = set(resume_norm_list)

        for js in job_skills_cleaned:
            js_norm = self._normalize_text(js)
            if not js_norm:
                continue

            is_matched = False
            js_canonical = skill_groups.get(js_norm) if skill_groups else None

            # Tier 1: Direct exact normalized match or taxonomy alias group match
            if js_norm in resume_norm_set:
                is_matched = True
            elif js_canonical:
                for r_norm in resume_norm_list:
                    if r_norm in skill_groups and skill_groups[r_norm] == js_canonical:
                        is_matched = True
                        break

            # Tier 2: Substring & Word boundary match against resume explicit skills
            if not is_matched:
                for r_raw, r_norm in zip(resume_skills_cleaned, resume_norm_list):
                    # Check if job skill word is contained in resume skill
                    pattern = r'\b' + re.escape(js_norm) + r'\b'
                    if re.search(pattern, r_norm):
                        is_matched = True
                        break
                    pattern_reverse = r'\b' + re.escape(r_norm) + r'\b'
                    if len(r_norm) > 2 and re.search(pattern_reverse, js_norm):
                        is_matched = True
                        break
                    # Singular/Plural soft match (e.g. pipeline vs pipelines)
                    if js_norm.rstrip('s') == r_norm.rstrip('s'):
                        is_matched = True
                        break
                    # Role inflection soft match (e.g. engineer vs engineering)
                    if 'engineer' in js_norm and 'engineer' in r_norm:
                        is_matched = True
                        break

            # Tier 3: Fallback text search using all skill variants/aliases from taxonomy
            if not is_matched and fallback_text:
                variants = [js_norm]
                if js_canonical and canonical_to_aliases and js_canonical in canonical_to_aliases:
                    variants = list(set(variants + canonical_to_aliases[js_canonical]))
                
                for variant in variants:
                    pattern = r'\b' + re.escape(variant) + r'\b'
                    if re.search(pattern, fallback_text):
                        is_matched = True
                        break
                    
                    # Suffix check in fallback text (e.g. singular/plural)
                    if variant.endswith('s') and len(variant) > 3:
                        pattern_sing = r'\b' + re.escape(variant[:-1]) + r'\b'
                        if re.search(pattern_sing, fallback_text):
                            is_matched = True
                            break
                    else:
                        pattern_plur = r'\b' + re.escape(variant + 's') + r'\b'
                        if re.search(pattern_plur, fallback_text):
                            is_matched = True
                            break
                    
                    # Role inflection fallback check
                    if 'engineering' in variant:
                        pattern_eng = r'\b' + re.escape(variant.replace('engineering', 'engineer')) + r'\b'
                        if re.search(pattern_eng, fallback_text):
                            is_matched = True
                            break

            if is_matched:
                matched_skills.append(js)
            else:
                missing_skills.append(js)

        score = (len(matched_skills) / len(job_skills_cleaned)) * 100.0

        return {
            "score": round(score, 2),
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

        pref_role_str = candidate.pref_role_type
        if pref_role_str and pref_role_str.strip().lower() in ("none", "null", ""):
            pref_role_str = None
            
        pref_loc_str = candidate.pref_locations
        if pref_loc_str and pref_loc_str.strip().lower() in ("none", "null", ""):
            pref_loc_str = None

        # 1. Role Type Match
        if pref_role_str:
            roles = [r.strip().lower() for r in pref_role_str.split(",") if r.strip()]
            if roles:
                job_title_lower = job.title.lower() if job.title else ""
                match = any(role in job_title_lower for role in roles)
                
                # Check taxonomy roles and their aliases
                if not match and job.taxonomy_job_role_id:
                    role_aliases_map = self._get_job_role_aliases()
                    job_role_aliases = role_aliases_map.get(job.taxonomy_job_role_id, [])
                    for role in roles:
                        role_norm = self._normalize_text(role)
                        if not role_norm:
                            continue
                        for ja in job_role_aliases:
                            ja_norm = self._normalize_text(ja)
                            if role_norm == ja_norm or role_norm in ja_norm or ja_norm in role_norm:
                                match = True
                                break
                        if match:
                            break
                            
                score_components.append(100.0 if match else 0.0)
                logger.debug(f"Logistics - Role Match check for candidate {candidate.id} against job {job.id} ({job.title}): preferred roles={roles}, job title={job_title_lower}, match={match}")

        # 2. Location Match
        if pref_loc_str:
            locations = [l.strip().lower() for l in pref_loc_str.split(",") if l.strip()]
            if locations:
                match = False
                city_name = job.city.name.lower() if job.city and job.city.name else ""
                state_name = job.state.name.lower() if job.state and job.state.name else ""
                country_name = job.country.name.lower() if job.country and job.country.name else ""
                
                # Check remote
                if "remote" in locations and job.work_mode and job.work_mode.name.lower() == "remote":
                    match = True
                else:
                    match = any(
                        loc in city_name or loc in state_name or loc in country_name
                        for loc in locations if loc != "remote"
                    )
                score_components.append(100.0 if match else 0.0)
                logger.debug(f"Logistics - Location Match check for candidate {candidate.id} against job {job.id} ({job.title}): preferred locations={locations}, job location={city_name}/{state_name}, match={match}")

        # 3. Salary Match
        if candidate.pref_min_salary is not None:
            if job.salary_max is not None:
                match = (job.salary_max >= candidate.pref_min_salary)
                score_components.append(100.0 if match else 0.0)
                logger.debug(f"Logistics - Salary Match check (max) for candidate {candidate.id} against job {job.id}: pref_min={candidate.pref_min_salary}, job_max={job.salary_max}, match={match}")
            elif job.salary_min is not None:
                match = (job.salary_min >= candidate.pref_min_salary)
                score_components.append(100.0 if match else 0.0)
                logger.debug(f"Logistics - Salary Match check (min) for candidate {candidate.id} against job {job.id}: pref_min={candidate.pref_min_salary}, job_min={job.salary_min}, match={match}")
            else:
                # Job has no salary specified
                score_components.append(100.0)
                logger.debug(f"Logistics - Salary Match check for candidate {candidate.id} against job {job.id}: job has no salary specified (default to 100).")

        if not score_components:
            return 100.0

        final_logistics = sum(score_components) / len(score_components)
        logger.debug(f"Candidate {candidate.id} against job {job.id}: Final logistics score component = {final_logistics}")
        return final_logistics

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
        # If the job posting has no extracted skills, exclude skills score and redistribute its weight (0.30)
        # proportionally among Semantic (40%), Experience (20%), and Logistics (10%).
        has_job_skills = bool(job.resolved_skills)
        if has_job_skills:
            final_score = (
                (semantic_score * self.WEIGHT_SEMANTIC) +
                (skills_score * self.WEIGHT_SKILLS) +
                (experience_score * self.WEIGHT_EXPERIENCE) +
                (logistics_score * self.WEIGHT_FILTERS)
            )
        else:
            skills_score = skills_eval["score"]
            total_weight = self.WEIGHT_SEMANTIC + self.WEIGHT_EXPERIENCE + self.WEIGHT_FILTERS
            final_score = (
                (semantic_score * (self.WEIGHT_SEMANTIC / total_weight)) +
                (experience_score * (self.WEIGHT_EXPERIENCE / total_weight)) +
                (logistics_score * (self.WEIGHT_FILTERS / total_weight))
            )
        
        logger.info(f"Resume {resume.id} matched with Job {job.id} ({job.title}) - Final Score: {round(final_score, 2)} (Semantic: {round(semantic_score, 2)}, Skills: {round(skills_score, 2)}, Experience: {round(experience_score, 2)}, Logistics: {round(logistics_score, 2)})")

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

