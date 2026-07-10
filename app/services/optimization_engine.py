import json
import logging
from typing import Dict, Any
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

    def optimize_section(self, job: JobPosting, section: ResumeSection) -> Dict[str, Any]:
        """
        Sends the specific ResumeSection and Job requirements to Gemini 1.5 Flash to get an optimized version.
        Returns a dictionary with the optimized text, missing keywords, and feedback.
        """
        job_skills_str = ", ".join(job.extracted_skills) if job.extracted_skills else "None specified"
        
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

# Export singleton instance
optimization_engine = GeminiOptimizationEngine()
