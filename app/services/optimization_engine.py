import json
import logging
from typing import Dict, Any, List, Optional
import google.generativeai as genai

from app.models.job import JobPosting
from app.models.resume import ResumeSection, SectionType
from app.core.config import settings

logger = logging.getLogger(__name__)

class GeminiOptimizationEngine:
    def __init__(self):
        # Configure Gemini with the API key from settings
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # Use gemini-3.1-flash-lite for fast, structured generation with stable high quota limits
        self.model = genai.GenerativeModel('gemini-3.1-flash-lite')

    def _get_system_instruction_for_section(self, section_type: SectionType) -> str:
        """
        Returns a modular, task-specific prompt based on the section being optimized.
        """
        base_instruction = (
            "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
            "against a target job description and provide structured JSON output.\n"
            "You MUST output raw JSON matching exactly this schema:\n"
            "{ \"optimized_content\": \"string\", \"missing_keywords\": [\"string\"], \"optimization_feedback\": \"string\" }\n"
        )

        if section_type == SectionType.SKILLS:
            return base_instruction + (
                "TASK: This is the SKILLS section. Do NOT write paragraphs or bullet points. "
                "Only extract, format, and return a clean comma-separated or newline-separated list of skills. "
                "Compare the candidate's existing skills with the job requirements and suggest missing technical keywords."
            )
        elif section_type == SectionType.EXPERIENCE:
            return base_instruction + (
                "TASK: This is the EXPERIENCE section. Rewrite the bullet points to use strong action verbs "
                "and quantify achievements where possible. Ensure the tone is highly professional. "
                "If the candidate's experience falls short of the job's minimum requirement, note it in the feedback."
            )
        elif section_type == SectionType.SUMMARY:
            return base_instruction + (
                "TASK: This is the SUMMARY section. Write a compelling, concise 3-4 line professional summary "
                "that weaves in the core requirements of the job description to hook the recruiter immediately."
            )
        else:
            return base_instruction + (
                "TASK: Optimize the provided content for professionalism, clarity, and alignment with the job description."
            )

    def _get_general_system_instruction_for_section(self, section_type: SectionType) -> str:
        """
        Returns a system instruction for general resume section polishing without job details.
        """
        base_instruction = (
            "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
            "and provide a generally polished, professional, and optimized version of it.\n"
            "You MUST output raw JSON matching exactly this schema:\n"
            "{ \"optimized_content\": \"string\", \"optimization_feedback\": \"string\" }\n"
        )

        if section_type == SectionType.SKILLS:
            return base_instruction + (
                "TASK: This is the SKILLS section. Format the skills into a clean, well-organized list. "
                "Correct any spelling/casing issues. Do not write paragraphs."
            )
        elif section_type == SectionType.EXPERIENCE:
            return base_instruction + (
                "TASK: This is the EXPERIENCE section. Rewrite the bullet points to use strong action verbs "
                "and quantify achievements/metrics where possible. Improve the professional tone and readability."
            )
        elif section_type == SectionType.SUMMARY:
            return base_instruction + (
                "TASK: This is the SUMMARY section. Write a compelling, concise 3-4 line professional summary "
                "that highlights the candidate's core strengths, experience, and value proposition."
            )
        else:
            return base_instruction + (
                "TASK: Optimize the provided content for professionalism, grammar, clarity, and impact."
            )

    def optimize_section_general(self, section: ResumeSection) -> Dict[str, Any]:
        """
        Sends the specific ResumeSection to Gemini to get a generally optimized version without target job context.
        """
        system_instruction = self._get_general_system_instruction_for_section(section.section_type)
        
        user_prompt = f"""
        {system_instruction}
        
        --- CANDIDATE'S ORIGINAL CONTENT ({section.section_type}) ---
        {section.original_content}
        
        Provide the JSON output now:
        """

        try:
            response = self.model.generate_content(
                user_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            parsed_result = json.loads(response.text)
            return {
                "optimized_content": parsed_result.get("optimized_content", section.original_content),
                "optimization_feedback": parsed_result.get("optimization_feedback", "")
            }
        except Exception as e:
            logger.error(f"Gemini General Optimization Failed: {e}")
            return {
                "error": str(e),
                "optimized_content": section.original_content,
                "optimization_feedback": "Failed to connect to the Gemini Optimization AI."
            }

    def optimize_section(self, job: JobPosting, section: ResumeSection, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Sends the specific ResumeSection and Job requirements to Gemini 1.5 Flash to get an optimized version.
        Returns a dictionary with the optimized text, missing keywords, and feedback.
        """
        job_skills = keywords if keywords is not None else job.resolved_skills
        job_skills_str = ", ".join(job_skills) if job_skills else "None specified"
        
        system_instruction = self._get_system_instruction_for_section(section.section_type)
        
        user_prompt = f"""
        {system_instruction}
        
        --- TARGET JOB ---
        Title: {job.title}
        Requirements: {job.description}
        Required Skills: {job_skills_str}
        Minimum Experience: {job.min_experience_years} years
        
        --- CANDIDATE'S ORIGINAL CONTENT ({section.section_type}) ---
        {section.original_content}
        
        Provide the JSON output now:
        """

        try:
            # Enforce JSON output natively in Gemini 1.5
            response = self.model.generate_content(
                user_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.3 # Low temperature for more deterministic, professional output
                )
            )
            
            # Parse the JSON response securely
            parsed_result = json.loads(response.text)
            
            # Ensure the required keys exist in case the LLM drifted
            return {
                "optimized_content": parsed_result.get("optimized_content", section.original_content),
                "missing_keywords": parsed_result.get("missing_keywords", []),
                "optimization_feedback": parsed_result.get("optimization_feedback", "")
            }
            
        except Exception as e:
            logger.error(f"Gemini Optimization Failed: {e}")
            return {
                "error": str(e),
                "optimized_content": section.original_content,
                "missing_keywords": [],
                "optimization_feedback": "Failed to connect to the Gemini Optimization AI."
            }

    def analyze_resume_fit(self, resume_content: str, job_description: str, embedding_score: int) -> Dict[str, Any]:
        """
        Compares candidate's resume content against a job description, taking into account
        a pre-calculated embedding match score. Returns status, gaps, and strengths using Gemini.
        """
        match_status = "low"
        if embedding_score >= 75:
            match_status = "high"
        elif embedding_score >= 50:
            match_status = "medium"

        system_instruction = (
            "You are an expert AI Applicant Tracking System (ATS) and Resume Evaluator.\n"
            "Your goal is to compare a candidate's resume content against a target job description and "
            "provide a structured JSON output.\n"
            "You MUST output raw JSON matching exactly this schema:\n"
            "{\n"
            "  \"match_status\": \"string\",\n"
            "  \"status_message\": \"string\",\n"
            "  \"gaps\": [\"string\"],\n"
            "  \"strengths\": [\"string\"]\n"
            "}\n"
            "Rules for evaluation:\n"
            "1. You are given a pre-calculated candidate match score of "
            f"{embedding_score} out of 100, which corresponds to the match status '{match_status}'.\n"
            "2. Set the 'match_status' field in your JSON output to exactly the provided status: "
            f"'{match_status}'.\n"
            "3. Write a status_message summarizing the fit, keeping it aligned with the match score of "
            f"{embedding_score}%. For low scores, be honest but encouraging (e.g. mention that it likely needs optimization).\n"
            "4. Under 'gaps', list up to 6 actionable bullet points describing missing skills, experience, or certifications based on the comparison, formatted as concise professional bullet points (e.g., 'Proficient in containerization using Docker, enabling efficient application deployment.').\n"
            "5. Under 'strengths', list up to 6 key areas of strong alignment or matching qualifications.\n"
            "6. For low match scores, list more 'gaps' than 'strengths'. For high match scores, list more 'strengths' and keep 'gaps' minimal or empty."
        )

        user_prompt = f"""
        {system_instruction}

        --- TARGET JOB DESCRIPTION ---
        {job_description}

        --- CANDIDATE RESUME CONTENT ---
        {resume_content}

        Provide the JSON output now:
        """

        try:
            response = self.model.generate_content(
                user_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            parsed_result = json.loads(response.text)
            return {
                "score": embedding_score,
                "match_status": match_status,
                "status_message": parsed_result.get("status_message", f"Your resume match score is {embedding_score}%."),
                "gaps": parsed_result.get("gaps", []),
                "strengths": parsed_result.get("strengths", [])
            }
        except Exception as e:
            logger.error(f"Gemini Resume Fit Analysis Failed: {e}")
            return {
                "error": str(e),
                "score": embedding_score,
                "match_status": match_status,
                "status_message": f"Failed to connect to the Gemini Optimization AI. Your calculated score is {embedding_score}%.",
                "gaps": [],
                "strengths": []
            }

    def get_resume_suggestions(self, resume_content: str, job_description: str, job_skills: List[str]) -> Dict[str, Any]:
        """
        Dynamically analyzes the current resume content against the job description and its skills
        to return missing keywords and a list of actionable AI suggestions.
        """
        system_instruction = (
            "You are an expert ATS (Applicant Tracking System) and Resume Consultant.\n"
            "Your task is to analyze the candidate's current resume content against the target job description "
            "and provide feedback in structured JSON format.\n"
            "You MUST output raw JSON matching exactly this schema:\n"
            "{\n"
            "  \"missing_keywords\": [\"string\"],\n"
            "  \"ai_suggestions\": [\n"
            "    {\n"
            "      \"title\": \"string\",\n"
            "      \"description\": \"string\",\n"
            "      \"impact\": \"high\" | \"medium\" | \"low\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "1. 'missing_keywords': Identify which of the following job-required skills are missing from "
            f"the candidate's resume: {', '.join(job_skills)}.\n"
            "   Only list skills that are NOT present in the resume content.\n"
            "2. 'ai_suggestions': Provide up to 4 actionable suggestions to improve the resume. "
            "Keep suggestions simple and short, and understandable"
            "Only suggest improvements for areas that are not already optimized.\n"
            "   - If the summary section is brief or lacks impact, suggest 'Enhance summary' with high impact.\n"
            "   - If the experience section lacks metrics/quantification, suggest 'Add more impact metrics' with high impact.\n"
            "   - If there are missing key skills, suggest 'Improve skills section' with medium impact.\n"
            "   - If certifications are missing but relevant to the job, suggest 'Add certifications' with medium/high impact.\n"
            "   - If a section has already been optimized or improved, DO NOT include the suggestion for that section."
        )

        user_prompt = f"""
        {system_instruction}

        --- TARGET JOB DESCRIPTION ---
        {job_description}

        --- CANDIDATE RESUME CONTENT ---
        {resume_content}

        Provide the JSON output now:
        """

        try:
            response = self.model.generate_content(
                user_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            parsed_result = json.loads(response.text)
            return {
                "missing_keywords": parsed_result.get("missing_keywords", []),
                "ai_suggestions": parsed_result.get("ai_suggestions", [])
            }
        except Exception as e:
            logger.error(f"Failed to generate resume suggestions: {e}")
            return {
                "missing_keywords": [],
                "ai_suggestions": []
            }

# Export singleton instance
optimization_engine = GeminiOptimizationEngine()
