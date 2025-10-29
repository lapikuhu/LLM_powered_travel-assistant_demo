"""Static stub hotel provider with deterministic data."""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session as DBSession

from app.providers.hotels.base import HotelProvider
from app.repositories.hotels import HotelRepository

logger = logging.getLogger(__name__)


class StaticStubHotelProvider(HotelProvider):
    """Static hotel provider with predefined data for development/testing."""
    
    def __init__(self, db: DBSession):
        super().__init__(db)
        self.hotel_repo = HotelRepository(db)
        self._initialize_hotels()
    
    def _initialize_hotels(self):
        """Initialize the database with stub hotel data."""
        # Define stub hotels for major cities
        stub_hotels = [
            # Athens, Greece
            {
                "provider": "stub",
                "external_id": "stub_athens_1",
                "name": "Hotel Grande Bretagne",
                "city": "Athens",
                "country": "Greece",
                "lat": 37.9755,
                "lon": 23.7348,
                "address": "Constitution Square, Athens",
                "rating": 5.0,
                "price_eur_per_night": 280.0,
                "url": "https://example.com/grande-bretagne",
            },
            {
                "provider": "stub",
                "external_id": "stub_athens_2",
                "name": "Hotel Plaka",
                "city": "Athens",
                "country": "Greece",
                "lat": 37.9719,
                "lon": 23.7285,
                "address": "Plaka District, Athens",
                "rating": 4.2,
                "price_eur_per_night": 120.0,
                "url": "https://example.com/hotel-plaka",
            },
            {
                "provider": "stub",
                "external_id": "stub_athens_3",
                "name": "Athens Budget Inn",
                "city": "Athens",
                "country": "Greece",
                "lat": 37.9838,
                "lon": 23.7275,
                "address": "Omonia Square, Athens",
                "rating": 3.5,
                "price_eur_per_night": 45.0,
                "url": "https://example.com/budget-inn",
            },
            # Paris, France
            {
                "provider": "stub",
                "external_id": "stub_paris_1",
                "name": "The Ritz Paris",
                "city": "Paris",
                "country": "France",
                "lat": 48.8681,
                "lon": 2.3282,
                "address": "Place Vendôme, Paris",
                "rating": 5.0,
                "price_eur_per_night": 850.0,
                "url": "https://example.com/ritz-paris",
            },
            {
                "provider": "stub",
                "external_id": "stub_paris_2",
                "name": "Hotel des Grands Boulevards",
                "city": "Paris",
                "country": "France",
                "lat": 48.8718,
                "lon": 2.3428,
                "address": "17 Boulevard Poissonnière, Paris",
                "rating": 4.3,
                "price_eur_per_night": 190.0,
                "url": "https://example.com/grands-boulevards",
            },
            {
                "provider": "stub",
                "external_id": "stub_paris_3",
                "name": "Hotel Jeanne d'Arc",
                "city": "Paris",
                "country": "France",
                "lat": 48.8534,
                "lon": 2.3626,
                "address": "3 Rue de Jarente, Paris",
                "rating": 3.8,
                "price_eur_per_night": 89.0,
                "url": "https://example.com/jeanne-darc",
            },
            # London, England
            {
                "provider": "stub",
                "external_id": "stub_london_1",
                "name": "Claridge's",
                "city": "London",
                "country": "United Kingdom",
                "lat": 51.5129,
                "lon": -0.1480,
                "address": "Brook Street, Mayfair, London",
                "rating": 5.0,
                "price_eur_per_night": 650.0,
                "url": "https://example.com/claridges",
            },
            {
                "provider": "stub",
                "external_id": "stub_london_2",
                "name": "The Z Hotel Piccadilly",
                "city": "London",
                "country": "United Kingdom",
                "lat": 51.5099,
                "lon": -0.1342,
                "address": "2 Leicester Square, London",
                "rating": 4.1,
                "price_eur_per_night": 160.0,
                "url": "https://example.com/z-hotel",
            },
            {
                "provider": "stub",
                "external_id": "stub_london_3",
                "name": "YHA London Central",
                "city": "London",
                "country": "United Kingdom",
                "lat": 51.5188,
                "lon": -0.1142,
                "address": "104 Bolsover Street, London",
                "rating": 3.6,
                "price_eur_per_night": 55.0,
                "url": "https://example.com/yha-central",
            },
            # Rome, Italy
            {
                "provider": "stub",
                "external_id": "stub_rome_1",
                "name": "Hotel de Russie",
                "city": "Rome",
                "country": "Italy",
                "lat": 41.9109,
                "lon": 12.4769,
                "address": "Via del Babuino, Rome",
                "rating": 5.0,
                "price_eur_per_night": 420.0,
                "url": "https://example.com/de-russie",
            },
            {
                "provider": "stub",
                "external_id": "stub_rome_2",
                "name": "Hotel Artemide",
                "city": "Rome",
                "country": "Italy",
                "lat": 41.9028,
                "lon": 12.4964,
                "address": "Via Nazionale, Rome",
                "rating": 4.2,
                "price_eur_per_night": 180.0,
                "url": "https://example.com/artemide",
            },
            {
                "provider": "stub",
                "external_id": "stub_rome_3",
                "name": "The RomeHello",
                "city": "Rome",
                "country": "Italy",
                "lat": 41.8967,
                "lon": 12.4822,
                "address": "Via Palestro, Rome",
                "rating": 3.9,
                "price_eur_per_night": 70.0,
                "url": "https://example.com/romehello",
            },
        ]
        
        # Create hotels in database if they don't exist
        for hotel_data in stub_hotels:
            existing = self.hotel_repo.get_hotel_by_external_id(
                provider="stub",
                external_id=hotel_data["external_id"]
            )
            if not existing:
                self.hotel_repo.create_or_update_hotel(**hotel_data)
                logger.info(f"Created stub hotel: {hotel_data['name']} in {hotel_data['city']}")
    
    async def search_hotels(self,
                            city: str,
                            country: Optional[str] = None,
                            budget_tier: str = "mid",
                            limit: int = 20,
                        ) -> List[Dict[str, Any]]:
        """Search for hotels using the stub data.
        Args:
            city (str): City name.
            country (Optional[str]): Country name.
            budget_tier (str): Budget tier ("budget", "mid", "premium").
            limit (int): Maximum number of hotels to return.
        Returns:
            List[Dict[str, Any]]: List of normalized hotel data.
        """
        logger.info(f"Searching stub hotels for {city}, tier: {budget_tier}")
        
        # Get hotels from database
        hotels = self.hotel_repo.search_hotels_by_city(
            city=city,
            budget_tier=budget_tier,
            limit=limit
        )
        
        # Normalize to expected format
        normalized_hotels = []
        for hotel in hotels:
            normalized_hotels.append({
                "hotel_id": str(hotel.id),
                "external_id": hotel.external_id,
                "name": hotel.name,
                "city": hotel.city,
                "country": hotel.country,
                "lat": hotel.lat,
                "lon": hotel.lon,
                "address": hotel.address,
                "rating": hotel.rating,
                "price_eur_per_night": hotel.price_eur_per_night,
                "url": hotel.url,
                "provider": "stub",
            })
        
        logger.info(f"Found {len(normalized_hotels)} stub hotels for {city}")
        return normalized_hotels
    
    def get_provider_name(self) -> str:
        """Get the provider name.
        Args:
            None
        Returns:
            str: Provider name.
        """
        return "stub"