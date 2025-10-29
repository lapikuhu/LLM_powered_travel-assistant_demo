"""Seed script to initialize stub hotel data.
Used for testing and development.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Hotel
from app.config import get_settings

def seed_hotels():
    """Seed the database with stub hotel data."""
    settings = get_settings()
    
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Check if hotels already exist
        existing_count = db.query(Hotel).filter(Hotel.provider == "stub").count()
        if existing_count > 0:
            print(f"Found {existing_count} existing stub hotels. Skipping seed.")
            return
        
        # Stub hotel data
        hotels_data = [
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
        
        # Create hotel records
        for hotel_data in hotels_data:
            hotel = Hotel(**hotel_data)
            db.add(hotel)
        
        db.commit()
        print(f"Successfully seeded {len(hotels_data)} stub hotels.")
        
    except Exception as e:
        print(f"Error seeding hotels: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_hotels()