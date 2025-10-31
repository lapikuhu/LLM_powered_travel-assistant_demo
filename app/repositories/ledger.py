"""LLM ledger repository for cost tracking and spend cap enforcement."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func, desc

from app.db.models import LLMLedger


class LedgerRepository:
    """Repository for LLM usage tracking."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def record_usage(self,
                    session_id: Optional[str],
                    model: str,
                    prompt_tokens: int,
                    completion_tokens: int,
                    cost_usd: float,
                    blocked_after: bool = False,
                ) -> LLMLedger:
        """Record LLM usage.
        Args:
            session_id (Optional[str]): Session identifier.
            model (str): Model name.
            prompt_tokens (int): Number of prompt tokens.
            completion_tokens (int): Number of completion tokens.
            cost_usd (float): Cost in USD.
            blocked_after (bool): Whether the usage was blocked after.
        Returns:
            LLMLedger: Created ledger entry.
        """
        now = datetime.utcnow()
        month_key = now.strftime("%Y-%m")
        
        ledger_entry = LLMLedger(
            session_id=session_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            month_key=month_key,
            blocked_after=blocked_after,
        )
        
        self.db.add(ledger_entry)
        self.db.commit()
        self.db.refresh(ledger_entry)
        
        return ledger_entry
    
    def get_monthly_spend(self, month_key: Optional[str] = None) -> float:
        """Get total spend for a month. Defaults to current month.
        Args:
            month_key (Optional[str]): Month in 'YYYY-MM' format. Defaults to current month.
        Returns:
            float: Total spend for the month.
        """
        if month_key is None:
            month_key = datetime.utcnow().strftime("%Y-%m")
        
        result = (
            self.db.query(func.sum(LLMLedger.cost_usd))
            .filter(LLMLedger.month_key == month_key)
            .scalar()
        )
        
        return result or 0.0
    
    def is_spend_cap_exceeded(self, cap_usd: float, month_key: Optional[str] = None) -> bool:
        """Check if monthly spend cap is exceeded.
        Args:
            cap_usd (float): Spend cap in USD.
            month_key (Optional[str]): Month in 'YYYY-MM' format. Defaults to current month.
        Returns:
            bool: True if spend cap is exceeded, False otherwise.
        """
        monthly_spend = self.get_monthly_spend(month_key)
        return monthly_spend >= cap_usd
    
    def get_monthly_stats(self, month_key: Optional[str] = None) -> Dict[str, Any]:
        """Get comprehensive monthly statistics.
        Args:
            month_key (Optional[str]): Month in 'YYYY-MM' format. Defaults to current month.
        Returns:
            Dict[str, Any]: Monthly statistics including total cost, tokens, calls, and blocked calls
        """
        if month_key is None:
            month_key = datetime.utcnow().strftime("%Y-%m")
        
        # Total spend and tokens
        totals = (
            self.db.query(
                func.sum(LLMLedger.cost_usd).label("total_cost"),
                func.sum(LLMLedger.prompt_tokens).label("total_prompt_tokens"),
                func.sum(LLMLedger.completion_tokens).label("total_completion_tokens"),
                func.count(LLMLedger.id).label("total_calls"),
            )
            .filter(LLMLedger.month_key == month_key)
            .first()
        )
        
        # Blocked calls count
        blocked_calls = (
            self.db.query(func.count(LLMLedger.id))
            .filter(
                LLMLedger.month_key == month_key,
                LLMLedger.blocked_after == True
            )
            .scalar() or 0
        )
        
        return {
            "month": month_key,
            "total_cost_usd": totals.total_cost or 0.0,
            "total_prompt_tokens": totals.total_prompt_tokens or 0,
            "total_completion_tokens": totals.total_completion_tokens or 0,
            "total_calls": totals.total_calls or 0,
            "blocked_calls": blocked_calls,
        }
    
    def get_recent_usage(self, limit: int = 50) -> List[LLMLedger]:
        """Get recent LLM usage entries.
        Args:
            limit (int): Number of recent entries to retrieve.
        Returns:
            List[LLMLedger]: List of recent ledger entries.
        """
        return (
            self.db.query(LLMLedger)
            .order_by(desc(LLMLedger.created_at))
            .limit(limit)
            .all()
        )
    
    def get_usage_by_session(self, session_id: str) -> List[LLMLedger]:
        """Get all LLM usage for a session.
        Args:
            session_id (str): Session identifier.
        Returns:
            List[LLMLedger]: List of ledger entries for the session.
        """
        return (
            self.db.query(LLMLedger)
            .filter(LLMLedger.session_id == session_id)
            .order_by(LLMLedger.created_at)
            .all()
        )
    
    def get_daily_costs(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily cost breakdown for the last N days.
        Args:
            days (int): Number of days to look back.
        Returns:
            List[Dict[str, Any]]: List of daily cost summaries.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        results = (
            self.db.query(
                func.date(LLMLedger.created_at).label("date"),
                func.sum(LLMLedger.cost_usd).label("cost"),
                func.count(LLMLedger.id).label("calls")
            )
            .filter(LLMLedger.created_at >= cutoff_date)
            .group_by(func.date(LLMLedger.created_at))
            .order_by(func.date(LLMLedger.created_at))
            .all()
        )
        
        # SQLite returns dates as strings (YYYY-MM-DD) while PostgreSQL returns date objects.
        # Normalize to ISO date string without assuming the type.
        def _to_iso_date(value: Any) -> Optional[str]:
            if value is None:
                return None
            try:
                from datetime import date as _date, datetime as _datetime
                if isinstance(value, _datetime):
                    return value.date().isoformat()
                if isinstance(value, _date):
                    return value.isoformat()
            except Exception:
                pass
            # Fallback: best-effort string conversion (works for SQLite 'YYYY-MM-DD')
            return str(value)

        return [
            {
                "date": _to_iso_date(result.date),
                "cost_usd": float(result.cost or 0),
                "calls": result.calls or 0
            }
            for result in results
        ]