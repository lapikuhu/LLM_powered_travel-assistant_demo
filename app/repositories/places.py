"""Places repository for database operations."""

from typing import List, Optional
from sqlalchemy.orm import Session as DBSession

from app.db.models import Place


class PlaceRepository:
    """Repository for place operations."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create_or_update_place(self,
                                provider: str,
                                external_id: str,
                                name: str,
                                lat: float,
                                lon: float,
                                categories: Optional[dict] = None,
                                rating: Optional[float] = None,
                                address: Optional[str] = None,
                                city: Optional[str] = None,
                                country: Optional[str] = None,
                                raw_json: Optional[dict] = None,
                            ) -> Place:
        """Create or update a place.
        Args:
            provider (str): Data provider name.
            external_id (str): External place identifier.
            name (str): Place name.
            lat (float): Latitude.
            lon (float): Longitude.
            categories (Optional[dict]): Categories/tags.
            rating (Optional[float]): Place rating.
            address (Optional[str]): Address.
            city (Optional[str]): City name.
            country (Optional[str]): Country name.
            raw_json (Optional[dict]): Raw JSON data from provider.
        Returns:
            Place: Created or updated place object.
        """
        # Try to find existing place
        place = (
            self.db.query(Place)
            .filter(Place.provider == provider, Place.external_id == external_id)
            .first()
        )
        
        if place:
            # Update existing
            place.name = name
            place.lat = lat
            place.lon = lon
            place.categories = categories
            place.rating = rating
            place.address = address
            place.city = city
            place.country = country
            place.raw_json = raw_json
        else:
            # Create new
            place = Place(
                provider=provider,
                external_id=external_id,
                name=name,
                lat=lat,
                lon=lon,
                categories=categories,
                rating=rating,
                address=address,
                city=city,
                country=country,
                raw_json=raw_json,
            )
            self.db.add(place)
        
        self.db.commit()
        self.db.refresh(place)
        return place
    
    def get_place(self, place_id: str) -> Optional[Place]:
        """Get place by ID.
        Args:
            place_id (str): Place identifier.
        Returns:
            Optional[Place]: Place object or None if not found.
        """
        return self.db.query(Place).filter(Place.id == place_id).first()
    
    def get_place_by_external_id(self, provider: str, external_id: str) -> Optional[Place]:
        """Get place by provider and external ID.
        Args:
            provider (str): Data provider name.
            external_id (str): External place identifier.
        Returns:
            Optional[Place]: Place object or None if not found.
        """
        return (
            self.db.query(Place)
            .filter(Place.provider == provider, Place.external_id == external_id)
            .first()
        )
    
    def search_places_by_city(self, city: str, limit: int = 50) -> List[Place]:
        """Search places by city.
        Args:
            city (str): City name.
            limit (int): Maximum number of results.
        Returns:
            List[Place]: List of places matching criteria.
        """
        return (
            self.db.query(Place)
            .filter(Place.city.ilike(f"%{city}%"))
            .limit(limit)
            .all()
        )
    
    def get_places_by_category(self, city: str, category: str, limit: int = 20) -> List[Place]:
        """Get places by city and category.
        Args:
            city (str): City name.
            category (str): Category to filter by.
            limit (int): Maximum number of results.
        Returns:
            List[Place]: List of places matching criteria.
        """
        return (
            self.db.query(Place)
            .filter(
                Place.city.ilike(f"%{city}%"),
                Place.categories.op("?")(category)  # JSONb contains operator
            )
            .limit(limit)
            .all()
        )