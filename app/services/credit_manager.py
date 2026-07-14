import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.candidate import Candidate

logger = logging.getLogger(__name__)

class CreditManager:
    """
    Manages checking and deducting credits for LLM and platform actions.
    Modular design allows rules to be easily updated or changed to section-wise deductions.
    """
    COST_RESUME_OPTIMIZATION = 15
    COST_COVER_LETTER_GENERATION = 15
    COST_SECTION_OPTIMIZATION = 10

    @classmethod
    def check_credits(cls, candidate: Candidate, cost: int, limits: dict) -> bool:
        """
        Checks if the candidate has enough credits remaining for the operation.
        """
        remaining = limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used
        return remaining >= cost

    @classmethod
    def check_and_deduct_credits(
        cls, 
        candidate: Candidate, 
        cost: int, 
        limits: dict, 
        db: Session
    ) -> None:
        """
        Validates if the candidate has enough credits remaining for the operation.
        If yes, deducts the credits and updates the database.
        If no, raises a 402 HTTP Payment Required exception.
        """
        remaining = limits["monthly_ai_credits"] - candidate.monthly_ai_credits_used
        if remaining < cost:
            logger.warning(
                f"Candidate {candidate.id} has insufficient credits: "
                f"Needs {cost}, Has {remaining} (Used {candidate.monthly_ai_credits_used}/{limits['monthly_ai_credits']})"
            )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Insufficient AI credits. This action costs {cost} AI credits, "
                    f"but you only have {max(0, remaining)} credits remaining this month."
                )
            )
            
        # Deduct credits
        candidate.monthly_ai_credits_used += cost
        db.add(candidate)
        logger.info(f"Deducted {cost} AI credits from candidate {candidate.id}. New used: {candidate.monthly_ai_credits_used}")

# Export singleton / class instance helper
credit_manager = CreditManager()
