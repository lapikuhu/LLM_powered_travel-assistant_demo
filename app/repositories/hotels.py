"""Hotels repository for database operations."""

from typing import List, Optional
from sqlalchemy.orm import Session as DBSession

from app.db.models import Hotel


class HotelRepository:
    """Repository for hotel operations."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create_or_update_hotel(
        self,
        provider: str,
        name: str,
        external_id: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        price_eur_per_night: Optional[float] = None,
        rating: Optional[float] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        url: Optional[str] = None,
        raw_json: Optional[dict] = None,
    ) -> Hotel:
        """Create or update a hotel."""
        # Try to find existing hotel by external_id if provided
        hotel = None
        if external_id:
            hotel = (
                self.db.query(Hotel)
                .filter(Hotel.provider == provider, Hotel.external_id == external_id)
                .first()
            )
        
        if hotel:
            # Update existing
            hotel.name = name
            hotel.lat = lat
            hotel.lon = lon
            hotel.price_eur_per_night = price_eur_per_night
            hotel.rating = rating
            hotel.address = address
            hotel.city = city
            hotel.country = country
            hotel.url = url
            hotel.raw_json = raw_json
        else:
            # Create new
            hotel = Hotel(
                provider=provider,
                external_id=external_id,
                name=name,
                lat=lat,
                lon=lon,
                price_eur_per_night=price_eur_per_night,
                rating=rating,
                address=address,
                city=city,
                country=country,
                url=url,
                raw_json=raw_json,
            )
            self.db.add(hotel)
        
        self.db.commit()
        self.db.refresh(hotel)
        return hotel
    
    def get_hotel(self, hotel_id: str) -> Optional[Hotel]:
        """Get hotel by ID."""
        return self.db.query(Hotel).filter(Hotel.id == hotel_id).first()
    
    def get_hotel_by_external_id(self, provider: str, external_id: str) -> Optional[Hotel]:
        """Get hotel by provider and external ID."""
        return (
            self.db.query(Hotel)
            .filter(Hotel.provider == provider, Hotel.external_id == external_id)
            .first()
        )
    
    def search_hotels_by_city(self, city: str, budget_tier: str, limit: int = 20) -> List[Hotel]:
        """Search hotels by city and budget tier."""
        query = self.db.query(Hotel).filter(Hotel.city.ilike(f"%{city}%"))
        
        # Filter by price range based on budget tier
        if budget_tier == "budget":
            query = query.filter(Hotel.price_eur_per_night <= 80)
        elif budget_tier == "mid":
            query = query.filter(
                Hotel.price_eur_per_night > 80,
                Hotel.price_eur_per_night <= 150
            )
        elif budget_tier == "premium":
            query = query.filter(Hotel.price_eur_per_night > 150)
        
        return query.order_by(Hotel.rating.desc().nullslast()).limit(limit).all()
    
    def get_hotels_by_price_range(
        self, city: str, min_price: float, max_price: float, limit: int = 20
    ) -> List[Hotel]:
        """Get hotels by city and price range."""
        return (
            self.db.query(Hotel)
            .filter(
                Hotel.city.ilike(f"%{city}%"),
                Hotel.price_eur_per_night >= min_price,
                Hotel.price_eur_per_night <= max_price,
            )
            .order_by(Hotel.rating.desc().nullslast())
            .limit(limit)
            .all()
        )