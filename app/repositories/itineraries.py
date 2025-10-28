"""Itinerary repository for database operations."""

from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session as DBSession, joinedload

from app.db.models import Itinerary, ItineraryDay, ItineraryItem


class ItineraryRepository:
    """Repository for itinerary operations."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create_itinerary(
        self,
        session_id: str,
        city: str,
        country: Optional[str],
        start_date: date,
        end_date: date,
        budget_tier: str,
    ) -> Itinerary:
        """Create a new itinerary."""
        itinerary = Itinerary(
            session_id=session_id,
            city=city,
            country=country,
            start_date=start_date,
            end_date=end_date,
            budget_tier=budget_tier,
        )
        self.db.add(itinerary)
        self.db.commit()
        self.db.refresh(itinerary)
        return itinerary
    
    def get_itinerary(self, itinerary_id: str) -> Optional[Itinerary]:
        """Get itinerary by ID with all related data."""
        return (
            self.db.query(Itinerary)
            .options(
                joinedload(Itinerary.days).joinedload(ItineraryDay.items)
            )
            .filter(Itinerary.id == itinerary_id)
            .first()
        )
    
    def get_itineraries_by_session(self, session_id: str) -> List[Itinerary]:
        """Get all itineraries for a session."""
        return (
            self.db.query(Itinerary)
            .filter(Itinerary.session_id == session_id)
            .order_by(Itinerary.created_at.desc())
            .all()
        )
    
    def create_day(self, itinerary_id: str, day_index: int, date_value: date) -> ItineraryDay:
        """Create a new day in an itinerary."""
        day = ItineraryDay(
            itinerary_id=itinerary_id,
            day_index=day_index,
            date=date_value,
        )
        self.db.add(day)
        self.db.commit()
        self.db.refresh(day)
        return day
    
    def create_item(
        self,
        day_id: str,
        item_type: str,
        ref_place_id: Optional[str] = None,
        ref_hotel_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ItineraryItem:
        """Create a new item in a day."""
        item = ItineraryItem(
            day_id=day_id,
            item_type=item_type,
            ref_place_id=ref_place_id,
            ref_hotel_id=ref_hotel_id,
            start_time=start_time,
            end_time=end_time,
            notes=notes,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item
    
    def get_item(self, item_id: str) -> Optional[ItineraryItem]:
        """Get item by ID."""
        return self.db.query(ItineraryItem).filter(ItineraryItem.id == item_id).first()
    
    def delete_item(self, item_id: str) -> bool:
        """Delete an item."""
        item = self.get_item(item_id)
        if item:
            self.db.delete(item)
            self.db.commit()
            return True
        return False
    
    def update_item_notes(self, item_id: str, notes: str) -> Optional[ItineraryItem]:
        """Update item notes."""
        item = self.get_item(item_id)
        if item:
            item.notes = notes
            self.db.commit()
            self.db.refresh(item)
        return item