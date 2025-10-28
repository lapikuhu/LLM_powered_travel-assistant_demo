"""Spend cap management for LLM usage."""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session as DBSession

from app.config import Settings
from app.repositories.ledger import LedgerRepository

logger = logging.getLogger(__name__)


class SpendCapManager:
    """Manages LLM spend cap enforcement."""
    
    def __init__(self, settings: Settings, db: DBSession):
        self.settings = settings
        self.db = db
        self.ledger_repo = LedgerRepository(db)
        self.monthly_cap_usd = settings.monthly_spend_cap_usd
    
    def is_spend_cap_exceeded(self, month_key: Optional[str] = None) -> bool:
        """Check if the monthly spend cap has been exceeded.
        Args:
            month_key (Optional[str]): Month in 'YYYY-MM' format. Defaults to current month
        Returns:
            bool: True if cap exceeded, False otherwise.
        """
        if month_key is None:
            month_key = datetime.utcnow().strftime("%Y-%m")
        
        return self.ledger_repo.is_spend_cap_exceeded(self.monthly_cap_usd, month_key)
    
    def get_remaining_budget(self, month_key: Optional[str] = None) -> float:
        """Get remaining budget for the month.
        Args:
            month_key (Optional[str]): Month in 'YYYY-MM' format. Defaults to current month
        Returns:
            float: Remaining budget in USD.
        """
        if month_key is None:
            month_key = datetime.utcnow().strftime("%Y-%m")
        
        spent = self.ledger_repo.get_monthly_spend(month_key)
        return max(0.0, self.monthly_cap_usd - spent)
    
    def get_spend_status(self, month_key: Optional[str] = None) -> dict:
        """Get comprehensive spend status.
        Args:
            month_key (Optional[str]): Month in 'YYYY-MM' format. Defaults to current month
        Returns:
            dict: Spend status including cap, spent, remaining, percentage used, and flags.
        """
        if month_key is None:
            month_key = datetime.utcnow().strftime("%Y-%m")
        
        spent = self.ledger_repo.get_monthly_spend(month_key)
        remaining = max(0.0, self.monthly_cap_usd - spent)
        percentage = (spent / self.monthly_cap_usd) * 100 if self.monthly_cap_usd > 0 else 0
        
        return {
            "month": month_key,
            "cap_usd": self.monthly_cap_usd,
            "spent_usd": spent,
            "remaining_usd": remaining,
            "percentage_used": percentage,
            "is_capped": spent >= self.monthly_cap_usd,
            "is_warning": percentage >= 80,  # Warning at 80%
        }
    
    def estimate_call_cost(self,
                            model: str,
                            prompt_tokens: int,
                            completion_tokens: int
                        ) -> float:
        """
        Estimate cost of an LLM call.
        Args:
            model (str): Model name (e.g., 'gpt-4', 'gpt-3.5-turbo').
            prompt_tokens (int): Number of prompt tokens.
            completion_tokens (int): Number of completion tokens.
        Returns:
            float: Estimated cost in USD.

        Note: These are approximate costs and may differ from actual billing.
        Update these rates based on your OpenAI pricing.
        """
        # Cost per 1K tokens (as of 2024, adjust as needed)
        pricing = {
            "gpt-4": {
                "prompt": 0.03,      # $0.03 per 1K prompt tokens
                "completion": 0.06   # $0.06 per 1K completion tokens
            },
            "gpt-4-turbo": {
                "prompt": 0.01,
                "completion": 0.03
            },
            "gpt-3.5-turbo": {
                "prompt": 0.0015,
                "completion": 0.002
            },
        }
        
        # Default to gpt-4 pricing if model not found
        model_pricing = pricing.get(model, pricing["gpt-4"])
        
        prompt_cost = (prompt_tokens / 1000) * model_pricing["prompt"]
        completion_cost = (completion_tokens / 1000) * model_pricing["completion"]
        
        return prompt_cost + completion_cost
    
    def can_make_call(
        self,
        model: str,
        estimated_prompt_tokens: int,
        estimated_completion_tokens: int
    ) -> bool:
        """Check if we can make an LLM call without exceeding budget.
        Args:
            model (str): Model name.
            estimated_prompt_tokens (int): Estimated prompt tokens.
            estimated_completion_tokens (int): Estimated completion tokens.
        Returns:
            bool: True if call can be made, False otherwise.
        """
        if self.is_spend_cap_exceeded():
            return False
        
        estimated_cost = self.estimate_call_cost(
            model, estimated_prompt_tokens, estimated_completion_tokens
        )
        
        remaining = self.get_remaining_budget()
        return estimated_cost <= remaining
    
    def record_llm_call(
        self,
        session_id: Optional[str],
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        actual_cost_usd: Optional[float] = None,
    ) -> None:
        """Record an LLM call in the ledger."""
        # Use estimated cost if actual cost not provided
        if actual_cost_usd is None:
            actual_cost_usd = self.estimate_call_cost(model, prompt_tokens, completion_tokens)
        
        # Check if this call puts us over the cap
        blocked_after = False
        if not self.is_spend_cap_exceeded():  # Before this call
            # Simulate the spend to see if it would exceed cap
            current_spend = self.ledger_repo.get_monthly_spend()
            if (current_spend + actual_cost_usd) >= self.monthly_cap_usd:
                blocked_after = True
        
        # Record in ledger
        self.ledger_repo.record_usage(
            session_id=session_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=actual_cost_usd,
            blocked_after=blocked_after,
        )
        
        if blocked_after:
            logger.warning(
                f"Monthly spend cap of ${self.monthly_cap_usd} reached after this call. "
                f"Future calls will be blocked."
            )
    
    def get_fallback_response(self) -> str:
        """Get a fallback response when spend cap is exceeded.
        Args:
            None
        Returns:
            str: Fallback message.
        """
        spend_status = self.get_spend_status()
        return (
            f"I'm sorry, but I've reached the monthly budget limit of "
            f"${self.monthly_cap_usd:.2f} for this service. "
            f"The budget will reset next month. "
            f"Currently spent: ${spend_status['spent_usd']:.2f}. "
            f"You can still view and export any itineraries you've already created."
        )