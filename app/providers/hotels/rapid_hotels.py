"""RapidAPI hotel provider implementation."""

import logging
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.orm import Session as DBSession

from app.config import Settings
from app.providers.hotels.base import HotelProvider
from app.repositories.hotels import HotelRepository
from app.repositories.cache import CacheRepository

logger = logging.getLogger(__name__)


class RapidAPIHotelProvider(HotelProvider):
    """Hotel provider using RapidAPI hotels endpoint."""
    
    def __init__(self, settings: Settings, db: DBSession):
        super().__init__(db)
        self.api_key = settings.rapidapi_key
        self.base_url = "https://booking-com.p.rapidapi.com/v1"
        self.cache_ttl = settings.api_cache_ttl_seconds
        self.hotel_repo = HotelRepository(db)
        self.cache_repo = CacheRepository(db)
        
        # HTTP client with timeout and headers
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "X-RapidAPI-Key": self.api_key,
                "X-RapidAPI-Host": "booking-com.p.rapidapi.com"
            }
        )
    
    async def search_hotels(
        self,
        city: str,
        country: Optional[str] = None,
        budget_tier: str = "mid",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search for hotels using RapidAPI."""
        if not self.api_key:
            logger.warning("RapidAPI key not configured, falling back to empty results")
            return []
        
        logger.info(f"Searching RapidAPI hotels for {city}, tier: {budget_tier}")
        
        # First, search for the location
        location_data = await self._search_location(city, country)
        if not location_data:
            logger.warning(f"Could not find location data for {city}")
            return []
        
        dest_id = location_data.get("dest_id")
        if not dest_id:
            logger.warning(f"Could not get destination ID for {city}")
            return []
        
        # Search for hotels
        hotels_data = await self._search_hotels_by_destination(
            dest_id=dest_id,
            city=city,
            budget_tier=budget_tier,
            limit=limit
        )
        
        return self._normalize_hotels(hotels_data, city, country)
    
    async def _search_location(self, city: str, country: Optional[str]) -> Optional[Dict[str, Any]]:
        """Search for location to get destination ID."""
        search_query = city
        if country:
            search_query = f"{city}, {country}"
        
        params = {
            "query": search_query,
            "locale": "en-us"
        }
        
        # Check cache
        cached = self.cache_repo.get_cached_response(
            provider="rapidapi_hotels",
            endpoint="locations",
            params=params
        )
        
        if cached:
            logger.info(f"Cache hit for location search: {search_query}")
            return cached.get("result", [{}])[0] if cached.get("result") else None
        
        try:
            url = f"{self.base_url}/locations/search"
            response = self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Cache the response
            self.cache_repo.cache_response(
                provider="rapidapi_hotels",
                endpoint="locations",
                params=params,
                response=data,
                ttl_seconds=self.cache_ttl * 24,  # Location data is more stable
            )
            
            results = data.get("result", [])
            if results:
                return results[0]  # Take first result
            
            return None
            
        except httpx.HTTPError as e:
            logger.error(f"RapidAPI location search error for {search_query}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in location search: {e}")
            return None
    
    async def _search_hotels_by_destination(
        self,
        dest_id: str,
        city: str,
        budget_tier: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Search hotels by destination ID."""
        
        # Convert budget tier to price range
        price_filters = self._get_price_filters(budget_tier)
        
        params = {
            "dest_id": dest_id,
            "order_by": "popularity",
            "adults_number": 2,
            "room_number": 1,
            "units": "metric",
            "locale": "en-us",
            "currency": "EUR",
            **price_filters
        }
        
        # Check cache
        cached = self.cache_repo.get_cached_response(
            provider="rapidapi_hotels",
            endpoint="hotels_search",
            params=params
        )
        
        if cached:
            logger.info(f"Cache hit for hotels search: {city}")
            return cached.get("result", [])
        
        try:
            url = f"{self.base_url}/hotels/search"
            response = self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Cache the response
            self.cache_repo.cache_response(
                provider="rapidapi_hotels",
                endpoint="hotels_search",
                params=params,
                response=data,
                ttl_seconds=self.cache_ttl,
            )
            
            results = data.get("result", [])
            return results[:limit]  # Limit results
            
        except httpx.HTTPError as e:
            logger.error(f"RapidAPI hotels search error for {city}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in hotels search: {e}")
            return []
    
    def _get_price_filters(self, budget_tier: str) -> Dict[str, Any]:
        """Get price filter parameters based on budget tier."""
        if budget_tier == "budget":
            return {"price_filter_currencycode": "EUR", "price_filter_max": "80"}
        elif budget_tier == "premium":
            return {"price_filter_currencycode": "EUR", "price_filter_min": "150"}
        else:  # mid
            return {
                "price_filter_currencycode": "EUR",
                "price_filter_min": "80",
                "price_filter_max": "150"
            }
    
    def _normalize_hotels(
        self,
        hotels_data: List[Dict[str, Any]],
        city: str,
        country: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Normalize hotel data from RapidAPI response."""
        normalized = []
        
        for hotel in hotels_data:
            try:
                # Extract basic info
                hotel_id = hotel.get("hotel_id", "")
                name = hotel.get("hotel_name", "Unknown Hotel")
                
                # Extract location
                lat = hotel.get("latitude")
                lon = hotel.get("longitude")
                address = hotel.get("address", "")
                
                # Extract pricing (convert to EUR if needed)
                price_data = hotel.get("min_total_price")
                price_eur = None
                if price_data and isinstance(price_data, (int, float)):
                    price_eur = float(price_data)
                
                # Extract rating
                rating = hotel.get("review_score")
                if rating:
                    rating = float(rating) / 2  # Convert from 0-10 to 0-5 scale
                
                # Create normalized hotel record
                normalized_hotel = {
                    "external_id": f"rapidapi_{hotel_id}",
                    "name": name,
                    "city": city,
                    "country": country,
                    "lat": lat,
                    "lon": lon,
                    "address": address,
                    "rating": rating,
                    "price_eur_per_night": price_eur,
                    "url": hotel.get("url", ""),
                    "provider": "rapidapi",
                    "raw_json": hotel,
                }
                
                # Store in database
                if hotel_id:
                    db_hotel = self.hotel_repo.create_or_update_hotel(**normalized_hotel)
                    normalized_hotel["hotel_id"] = str(db_hotel.id)
                
                normalized.append(normalized_hotel)
                
            except Exception as e:
                logger.warning(f"Error normalizing hotel data: {e}")
                continue
        
        logger.info(f"Normalized {len(normalized)} hotels from RapidAPI")
        return normalized
    
    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "rapidapi"
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except Exception:
            pass  # Ignore errors during cleanup