"""Base hotel provider interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session as DBSession


class HotelProvider(ABC):
    """Abstract base class for hotel providers."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    @abstractmethod
    async def search_hotels(
        self,
        city: str,
        country: Optional[str] = None,
        budget_tier: str = "mid",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search for hotels in a city.
        
        Args:
            city: The city name
            country: Optional country name for better matching
            budget_tier: "budget", "mid", or "premium"
            limit: Maximum number of hotels to return
            
        Returns:
            List of normalized hotel data
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        pass