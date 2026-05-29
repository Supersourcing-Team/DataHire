import os
import json
import anthropic
from typing import Dict, Any

from app.models.job import JobPosting
from app.models.resume import ResumeSection
from app.core.config import settings

class OptimizationEngine:
    def __init__(self):
        # We rely on settings.ANTHROPIC_API_KEY from config
        self.client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )

    def optimize_section(self, job: JobPosting, section: ResumeSection) -> Dict[str, Any]:
        """
        Sends the specific ResumeSection and Job requirements to Anthropic AI to get an optimized version.
        Returns a dictionary with the optimized text and missing keywords analysis.
        """
        
        job_skills_str = ", ".join(job.extracted_skills) if job.extracted_skills else "None specified"
        
        system_prompt = (
            "You are an expert AI Resume Optimizer. Your goal is to rewrite specific sections of a candidate's resume "
            "to better match a target job description, while maintaining complete honesty. "
            "You must output your response in raw JSON format matching exactly this schema: "
            "{ 'optimized_content': 'string', 'missing_keywords': ['string'], 'optimization_feedback': 'string' }"
        )
        
        user_prompt = f"""
        Target Job Title: {job.title}
        Target Job Description: {job.description}
        Target Job Required Skills: {job_skills_str}
        
        Please optimize the following {section.section_type} section from the candidate's resume.
        Add any relevant missing keywords that the candidate might possess but didn't explicitly state.
        Paraphrase statements to have a highly professional tone.
        Highlight if they lack required experience for this section.
        
        Original {section.section_type} Content:
        {section.original_content}
        """

        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Parse the JSON response
            result_text = response.content[0].text
            # Clean up the response in case the model added markdown blocks
            if result_text.startswith("```json"):
                result_text = result_text.replace("```json\n", "").replace("\n```", "")
                
            parsed_result = json.loads(result_text)
            return parsed_result
            
        except Exception as e:
            return {
                "error": str(e),
                "optimized_content": section.original_content,
                "missing_keywords": [],
                "optimization_feedback": "Failed to connect to the Optimization AI."
            }
