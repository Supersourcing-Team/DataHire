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

    def _get_system_instruction_for_section(self, section_type: SectionType, has_structured: bool = False) -> str:
        """
        Returns a modular, task-specific prompt based on the section being optimized.
        """
        try:
            section_type = SectionType(section_type)
        except ValueError:
            section_type = SectionType.OTHER

        if has_structured:
            base_instruction = (
                "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
                "against a target job description and provide structured JSON output.\n"
                "You MUST output raw JSON matching exactly this schema:\n"
                "{\n"
                "  \"optimized_content\": \"string\",\n"
                "  \"optimized_structured_content\": <any JSON matching original structured schema>,\n"
                "  \"missing_keywords\": [\"string\"],\n"
                "  \"optimization_feedback\": \"string\"\n"
                "}\n"
            )
        else:
            base_instruction = (
                "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
                "against a target job description and provide structured JSON output.\n"
                "You MUST output raw JSON matching exactly this schema:\n"
                "{\n"
                "  \"optimized_content\": \"string\",\n"
                "  \"missing_keywords\": [\"string\"],\n"
                "  \"optimization_feedback\": \"string\"\n"
                "}\n"
            )

        if section_type == SectionType.SKILLS:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the SKILLS section. You MUST output raw JSON matching the required schema.\n"
                    "For 'optimized_structured_content', you are given a dictionary with 'technical', 'soft', and 'tools' keys (lists of strings).\n"
                    "Inject the missing keywords from the job description into the appropriate list (usually 'technical') in that dictionary and return it.\n"
                    "For 'optimized_content', return a clean, categorized, comma-separated plain-text string representation of all skills."
                )
            else:
                return base_instruction + (
                    "TASK: This is the SKILLS section. Do NOT write paragraphs or bullet points. "
                    "Only extract, format, and return a clean comma-separated or newline-separated list of skills. "
                    "Compare the candidate's existing skills with the job requirements and suggest missing technical keywords. "
                    "Most importantly, you MUST append the missing keywords from the job requirements (the 'Required Skills' list) "
                    "to the 'optimized_content' list of skills so that the optimized version actually contains them."
                )
        elif section_type == SectionType.EXPERIENCE:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the EXPERIENCE section. You MUST output raw JSON matching the required schema.\n"
                    "For 'optimized_structured_content', you are given a list of experience entries.\n"
                    "For each experience entry, rewrite its 'bullets' list of strings to use strong action verbs, quantify achievements, "
                    "and naturally weave in target keywords. You MUST preserve all other fields (like company, role, location, startDate, endDate) exactly as they are.\n"
                    "For 'optimized_content', return a clean, readable plain-text representation of all experiences, preserving their headers and original formatting."
                )
            else:
                return base_instruction + (
                    "TASK: This is the EXPERIENCE section. Rewrite the bullet points to use strong action verbs "
                    "and quantify achievements where possible. Ensure the tone is highly professional. "
                    "If the candidate's experience falls short of the job's minimum requirement, note it in the feedback. "
                    "Weave in the missing keywords/skills from the job requirements naturally where they fit the candidate's "
                    "responsibilities so that they are present in the experience content."
                )
        elif section_type == SectionType.PROJECTS:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the PROJECTS section. You MUST output raw JSON matching the required schema.\n"
                    "For 'optimized_structured_content', you are given a list of projects.\n"
                    "For each project, rewrite its 'description' and/or 'bullets' list of strings to use strong action verbs, professional tone, "
                    "and weave in missing keywords naturally where they fit. You MUST preserve all other fields (like title, techStack, link) exactly as they are.\n"
                    "For 'optimized_content', return a clean, readable plain-text representation of all projects, preserving their titles and original formatting."
                )
            else:
                return base_instruction + (
                    "TASK: Optimize the provided content for professionalism, clarity, and alignment with the job description."
                )
        elif section_type == SectionType.SUMMARY:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the SUMMARY section. You MUST output raw JSON matching the required schema.\n"
                    "For 'optimized_structured_content', rewrite/polish the summary text and return it as a dictionary with a 'text' key (e.g. {\"text\": \"optimized summary...\"}).\n"
                    "For 'optimized_content', return the same optimized summary as a raw string."
                )
            else:
                return base_instruction + (
                    "TASK: This is the SUMMARY section. Write a compelling, concise 3-4 line professional summary "
                    "that weaves in the core requirements of the job description and missing keywords/skills to hook the recruiter immediately."
                )
        elif section_type == SectionType.EDUCATION:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the EDUCATION section. You MUST output raw JSON matching the required schema.\n"
                    "For 'optimized_structured_content', return the same education entries as the original JSON list, but check for spelling, professional formatting, and capitalization.\n"
                    "For 'optimized_content', return a clean, readable plain-text representation of all education entries."
                )
            else:
                return base_instruction + (
                    "TASK: Optimize the provided content for professionalism, clarity, and alignment with the job description."
                )
        elif section_type == SectionType.CERTIFICATIONS:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the CERTIFICATIONS section. You MUST output raw JSON matching the required schema.\n"
                    "For 'optimized_structured_content', return the certifications JSON list. You may clean spelling or titles.\n"
                    "For 'optimized_content', return a clean, readable plain-text representation of all certifications."
                )
            else:
                return base_instruction + (
                    "TASK: Optimize the provided content for professionalism, clarity, and alignment with the job description."
                )
        else:
            return base_instruction + (
                "TASK: Optimize the provided content for professionalism, clarity, and alignment with the job description."
            )

    def _get_general_system_instruction_for_section(self, section_type: SectionType, has_structured: bool = False) -> str:
        """
        Returns a system instruction for general resume section polishing without job details.
        """
        try:
            section_type = SectionType(section_type)
        except ValueError:
            section_type = SectionType.OTHER

        if has_structured:
            base_instruction = (
                "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
                "and provide a generally polished, professional, and optimized version of it.\n"
                "You MUST output raw JSON matching exactly this schema:\n"
                "{\n"
                "  \"optimized_content\": \"string\",\n"
                "  \"optimized_structured_content\": <any JSON matching original structured schema>,\n"
                "  \"optimization_feedback\": \"string\"\n"
                "}\n"
            )
        else:
            base_instruction = (
                "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
                "and provide a generally polished, professional, and optimized version of it.\n"
                "You MUST output raw JSON matching exactly this schema:\n"
                "{\n"
                "  \"optimized_content\": \"string\",\n"
                "  \"optimization_feedback\": \"string\"\n"
                "}\n"
            )

        if section_type == SectionType.SKILLS:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the SKILLS section. Format the skills into a clean, well-organized list in 'optimized_structured_content' keeping 'technical', 'soft', and 'tools' keys.\n"
                    "Correct any spelling/casing issues. For 'optimized_content', return a clean categorized string representation."
                )
            else:
                return base_instruction + (
                    "TASK: This is the SKILLS section. Format the skills into a clean, well-organized list. "
                    "Correct any spelling/casing issues. Do not write paragraphs."
                )
        elif section_type == SectionType.EXPERIENCE:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the EXPERIENCE section. Rewrite the bullet points of each entry in 'optimized_structured_content' to use strong action verbs "
                    "and quantify achievements/metrics where possible. Improve the professional tone and readability. Preserve other fields exactly.\n"
                    "For 'optimized_content', return a clean plain-text string representation preserving headers."
                )
            else:
                return base_instruction + (
                    "TASK: This is the EXPERIENCE section. Rewrite the bullet points to use strong action verbs "
                    "and quantify achievements/metrics where possible. Improve the professional tone and readability."
                )
        elif section_type == SectionType.SUMMARY:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the SUMMARY section. Write a compelling, concise 3-4 line professional summary. "
                    "The 'optimized_structured_content' should be a dictionary with a single key 'text' containing this optimized summary.\n"
                    "For 'optimized_content', return it as a raw string."
                )
            else:
                return base_instruction + (
                    "TASK: This is the SUMMARY section. Write a compelling, concise 3-4 line professional summary "
                    "that highlights the candidate's core strengths, experience, and value proposition."
                )
        elif section_type == SectionType.EDUCATION:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the EDUCATION section. Polishing for grammar and style. Output original JSON list in 'optimized_structured_content'.\n"
                    "For 'optimized_content', return a clean plain-text string representation."
                )
            else:
                return base_instruction + (
                    "TASK: Optimize the provided content for professionalism, grammar, clarity, and impact."
                )
        elif section_type == SectionType.CERTIFICATIONS:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the CERTIFICATIONS section. Polishing titles. Output original JSON list in 'optimized_structured_content'.\n"
                    "For 'optimized_content', return a clean plain-text string representation."
                )
            else:
                return base_instruction + (
                    "TASK: Optimize the provided content for professionalism, grammar, clarity, and impact."
                )
        else:
            return base_instruction + (
                "TASK: Optimize the provided content for professionalism, grammar, clarity, and impact."
            )

    def optimize_section_general(self, section: ResumeSection) -> Dict[str, Any]:
        """
        Sends the specific ResumeSection to Gemini to get a generally optimized version without target job context.
        """
        has_structured = section.structured_content is not None
        system_instruction = self._get_general_system_instruction_for_section(section.section_type, has_structured=has_structured)
        
        original_structured_str = ""
        if has_structured:
            original_structured_str = (
                f"\n--- CANDIDATE'S ORIGINAL STRUCTURED JSON ({section.section_type}) ---\n"
                f"{json.dumps(section.structured_content, indent=2)}\n"
                "\nCRITICAL REQUIREMENT:\n"
                "You MUST return the exact same JSON structure in 'optimized_structured_content', retaining all "
                "original fields (such as 'id', 'company', 'role', 'startDate', 'endDate', 'location', 'institution', 'degree', 'title', etc.) exactly as they are. "
                "DO NOT discard or replace these fields with null or 'N/A'. Only polish/optimize the text within 'bullets', 'description', or 'text' fields.\n"
            )

        user_prompt = f"""
        {system_instruction}
        
        {original_structured_str if has_structured else f'''--- CANDIDATE RESUME CONTENT ({section.section_type}) ---
        {section.original_content}'''}
        
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
                "optimized_structured_content": parsed_result.get("optimized_structured_content") if has_structured else None,
                "optimization_feedback": parsed_result.get("optimization_feedback", "")
            }
        except Exception as e:
            logger.error(f"Gemini General Optimization Failed: {e}")
            return {
                "error": str(e),
                "optimized_content": section.original_content,
                "optimized_structured_content": section.structured_content if has_structured else None,
                "optimization_feedback": "Failed to connect to the Gemini Optimization AI."
            }

    def optimize_section(self, job: JobPosting, section: ResumeSection, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Sends the specific ResumeSection and Job requirements to Gemini 1.5 Flash to get an optimized version.
        Returns a dictionary with the optimized text, missing keywords, and feedback.
        """
        job_skills = keywords if keywords is not None else job.resolved_skills
        job_skills_str = ", ".join(job_skills) if job_skills else "None specified"
        
        has_structured = section.structured_content is not None
        system_instruction = self._get_system_instruction_for_section(section.section_type, has_structured=has_structured)
        
        original_structured_str = ""
        if has_structured:
            original_structured_str = (
                f"\n--- CANDIDATE'S ORIGINAL STRUCTURED JSON ({section.section_type}) ---\n"
                f"{json.dumps(section.structured_content, indent=2)}\n"
                "\nCRITICAL REQUIREMENT:\n"
                "You MUST return the exact same JSON structure in 'optimized_structured_content', retaining all "
                "original fields (such as 'id', 'company', 'role', 'startDate', 'endDate', 'location', 'institution', 'degree', 'title', etc.) exactly as they are. "
                "DO NOT discard or replace these fields with null or 'N/A'. Only polish/optimize the text within 'bullets', 'description', or 'text' fields to weave in the target keywords.\n"
            )

        user_prompt = f"""
        {system_instruction}
        
        --- TARGET JOB ---
        Title: {job.title}
        Requirements: {job.description}
        Required Skills: {job_skills_str}
        Minimum Experience: {job.min_experience_years} years
        
        {original_structured_str if has_structured else f'--- CANDIDATE RESUME CONTENT ({section.section_type}) ---\n{section.original_content}'}
        
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
                "optimized_structured_content": parsed_result.get("optimized_structured_content") if has_structured else None,
                "missing_keywords": parsed_result.get("missing_keywords", []),
                "optimization_feedback": parsed_result.get("optimization_feedback", "")
            }
            
        except Exception as e:
            logger.error(f"Gemini Optimization Failed: {e}")
            return {
                "error": str(e),
                "optimized_content": section.original_content,
                "optimized_structured_content": section.structured_content if has_structured else None,
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
            "2. 'ai_suggestions': Provide all actionable suggestions to improve the resume in a single go. "
            "Do NOT limit the number of suggestions; list all areas that need improvement. "
            "Keep suggestions simple, short, and understandable.\n"
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
                    temperature=0.0
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

    def analyze_resume_general_fit(self, resume_content: str, target_role: str) -> Dict[str, Any]:
        """
        Compares candidate's resume content against typical requirements for a target role.
        Returns gaps and strengths using Gemini.
        """
        system_instruction = (
            "You are an expert AI Career Coach and Resume Evaluator.\n"
            "Your goal is to compare a candidate's resume content against the typical expectations for a target role "
            "and provide a structured JSON output.\n"
            "You MUST output raw JSON matching exactly this schema:\n"
            "{\n"
            "  \"gaps\": [\"string\"],\n"
            "  \"strengths\": [\"string\"]\n"
            "}\n"
            "Rules for evaluation:\n"
            "1. Under 'gaps', list up to 6 actionable bullet points describing missing skills, experience, or certifications based on the comparison, formatted as concise professional bullet points.\n"
            "2. Under 'strengths', list up to 6 key areas of strong alignment or matching qualifications.\n"
        )

        user_prompt = f"""
        {system_instruction}

        --- TARGET ROLE ---
        {target_role}

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
                "target_role": target_role,
                "gaps": parsed_result.get("gaps", []),
                "strengths": parsed_result.get("strengths", [])
            }
        except Exception as e:
            logger.error(f"Gemini General Resume Fit Analysis Failed: {e}")
            return {
                "error": str(e),
                "target_role": target_role,
                "gaps": [],
                "strengths": []
            }

    def get_general_resume_suggestions(self, resume_content: str, target_role: str) -> Dict[str, Any]:
        """
        Dynamically analyzes the current resume content against the typical expectations for a target role
        to return missing/recommended keywords.
        """
        system_instruction = (
            "You are an expert ATS (Applicant Tracking System) and Resume Consultant.\n"
            "Your task is to analyze the candidate's current resume content against the typical expectations for the target role "
            "and suggest relevant skills, technologies, or keywords that are missing or should be highlighted.\n"
            "You MUST output raw JSON matching exactly this schema:\n"
            "{\n"
            "  \"suggested_keywords\": [\"string\"]\n"
            "}\n"
            "Rules:\n"
            "1. 'suggested_keywords': Identify which core professional or technical skills typical of the target role are missing from or could be strengthened in the candidate's resume.\n"
            "   Only suggest keywords that are NOT prominently present in the resume content, or would add value."
        )

        user_prompt = f"""
        {system_instruction}

        --- TARGET ROLE ---
        {target_role}

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
                "suggested_keywords": parsed_result.get("suggested_keywords", [])
            }
        except Exception as e:
            logger.error(f"Failed to generate general resume suggestions: {e}")
            return {
                "suggested_keywords": []
            }

    def _get_general_system_instruction_for_section_with_keywords(self, section_type: SectionType, target_role: str, keywords: List[str], has_structured: bool = False) -> str:
        try:
            section_type = SectionType(section_type)
        except ValueError:
            section_type = SectionType.OTHER

        if has_structured:
            base_instruction = (
                "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
                f"and provide a generally polished, professional, and optimized version of it tailored for a '{target_role}' role.\n"
                "You MUST output raw JSON matching exactly this schema:\n"
                "{\n"
                "  \"optimized_content\": \"string\",\n"
                "  \"optimized_structured_content\": <any JSON matching original structured schema>,\n"
                "  \"optimization_feedback\": \"string\"\n"
                "}\n"
                f"You MUST weave in these keywords naturally if possible: {', '.join(keywords)}.\n"
            )
        else:
            base_instruction = (
                "You are an expert AI Resume Optimizer. Your goal is to review a candidate's resume section "
                f"and provide a generally polished, professional, and optimized version of it tailored for a '{target_role}' role.\n"
                "You MUST output raw JSON matching exactly this schema:\n"
                "{\n"
                "  \"optimized_content\": \"string\",\n"
                "  \"optimization_feedback\": \"string\"\n"
                "}\n"
                f"You MUST weave in these keywords naturally if possible: {', '.join(keywords)}.\n"
            )

        if section_type == SectionType.SKILLS:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the SKILLS section. You MUST output raw JSON matching the required schema.\n"
                    "For 'optimized_structured_content', you are given a dictionary with 'technical', 'soft', and 'tools' keys (lists of strings).\n"
                    "Inject the target keywords into the appropriate list (usually 'technical') in that dictionary and return it.\n"
                    "For 'optimized_content', return a clean, categorized, comma-separated plain-text string representation of all skills."
                )
            else:
                return base_instruction + (
                    "TASK: This is the SKILLS section. Do NOT write paragraphs or bullet points. "
                    "Only return a clean comma-separated or newline-separated list of skills, appending/including the target keywords."
                )
        elif section_type == SectionType.EXPERIENCE:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the EXPERIENCE section. Rewrite the bullet points of each entry in 'optimized_structured_content' to use strong action verbs "
                    "and quantify achievements where possible. Weave in the target keywords naturally. Preserve other fields exactly.\n"
                    "For 'optimized_content', return a clean plain-text representation preserving headers."
                )
            else:
                return base_instruction + (
                    "TASK: This is the EXPERIENCE section. Rewrite the bullet points to use strong action verbs "
                    "and quantify achievements where possible. Weave in the target keywords naturally."
                )
        elif section_type == SectionType.SUMMARY:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the SUMMARY section. Write a compelling, concise 3-4 line professional summary "
                    "weaving in the target keywords and target role. The 'optimized_structured_content' should be a dictionary with a single key 'text' containing this optimized summary.\n"
                    "For 'optimized_content', return it as a raw string."
                )
            else:
                return base_instruction + (
                    "TASK: This is the SUMMARY section. Write a compelling, concise 3-4 line professional summary "
                    "weaving in the target keywords and target role to hook recruiters."
                )
        elif section_type == SectionType.EDUCATION:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the EDUCATION section. Polishing for grammar and style. Output original JSON list in 'optimized_structured_content'.\n"
                    "For 'optimized_content', return a clean plain-text string representation."
                )
            else:
                return base_instruction + (
                    "TASK: Optimize the provided content for professionalism, clarity, and impact."
                )
        elif section_type == SectionType.CERTIFICATIONS:
            if has_structured:
                return base_instruction + (
                    "TASK: This is the CERTIFICATIONS section. Polishing titles. Output original JSON list in 'optimized_structured_content'.\n"
                    "For 'optimized_content', return a clean plain-text string representation."
                )
            else:
                return base_instruction + (
                    "TASK: Optimize the provided content for professionalism, clarity, and impact."
                )
        else:
            return base_instruction + (
                "TASK: Optimize the provided content for professionalism, clarity, and impact."
            )

    def optimize_section_general_with_keywords(self, section: ResumeSection, target_role: str, keywords: List[str]) -> Dict[str, Any]:
        """
        Sends the specific ResumeSection to Gemini to get a generally optimized version tailored to a target role and keywords.
        """
        try:
            s_type = SectionType(section.section_type)
        except ValueError:
            s_type = SectionType.OTHER

        has_structured = section.structured_content is not None
        system_instruction = self._get_general_system_instruction_for_section_with_keywords(s_type, target_role, keywords, has_structured=has_structured)

        original_structured_str = ""
        if has_structured:
            original_structured_str = (
                f"\n--- CANDIDATE'S ORIGINAL STRUCTURED JSON ({section.section_type}) ---\n"
                f"{json.dumps(section.structured_content, indent=2)}\n"
                "\nCRITICAL REQUIREMENT:\n"
                "You MUST return the exact same JSON structure in 'optimized_structured_content', retaining all "
                "original fields (such as 'id', 'company', 'role', 'startDate', 'endDate', 'location', 'institution', 'degree', 'title', etc.) exactly as they are. "
                "DO NOT discard or replace these fields with null or 'N/A'. Only polish/optimize the text within 'bullets', 'description', or 'text' fields to weave in target keywords.\n"
            )

        user_prompt = f"""
        {system_instruction}

        {original_structured_str if has_structured else f'--- CANDIDATE RESUME CONTENT ({section.section_type}) ---\n{section.original_content}'}

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
                "optimized_structured_content": parsed_result.get("optimized_structured_content") if has_structured else None,
                "optimization_feedback": parsed_result.get("optimization_feedback", "")
            }
        except Exception as e:
            logger.error(f"Gemini General Optimization With Keywords Failed: {e}")
            return {
                "optimized_content": section.original_content,
                "optimized_structured_content": section.structured_content if has_structured else None,
                "optimization_feedback": "Failed to connect to the Gemini Optimization AI."
            }

# Export singleton instance
optimization_engine = GeminiOptimizationEngine()
