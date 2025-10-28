"""SQLAlchemy database models."""

import uuid
from datetime import datetime, date, time
from typing import Optional

from sqlalchemy import (
    Column, String, DateTime, Date, Time, Integer, Float, Boolean,
    Text, ForeignKey, Index, CheckConstraint, UniqueConstraint, TypeDecorator, JSON
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQL_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    
    Uses PostgreSQL's UUID type when available,
    otherwise uses CHAR(36), storing as stringified hex values.
    """
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PostgreSQL_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return str(value)
            else:
                return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            else:
                return value


class JSONColumn(TypeDecorator):
    """Platform-independent JSON type.
    
    Uses PostgreSQL's JSONB when available,
    otherwise uses JSON.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(JSON())


class Session(Base):
    """User session model."""
    __tablename__ = "sessions"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, nullable=False, default=func.now())
    ip_hash = Column(String(16), nullable=False, index=True)
    
    # Relationships
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    itineraries = relationship("Itinerary", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_sessions_ip_hash', 'ip_hash'),
    )


class Message(Base):
    """Chat message model."""
    __tablename__ = "messages"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id = Column(GUID(), ForeignKey("sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    # Relationships
    session = relationship("Session", back_populates="messages")
    
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="check_message_role"),
        Index('idx_messages_session_created', 'session_id', 'created_at'),
    )


class Itinerary(Base):
    """Travel itinerary model."""
    __tablename__ = "itineraries"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id = Column(GUID(), ForeignKey("sessions.id"), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    country = Column(String(100), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    budget_tier = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    # Relationships
    session = relationship("Session", back_populates="itineraries")
    days = relationship("ItineraryDay", back_populates="itinerary", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("budget_tier IN ('budget', 'mid', 'premium')", name="check_budget_tier"),
        Index('idx_itineraries_city', 'city'),
        Index('idx_itineraries_session', 'session_id'),
    )


class ItineraryDay(Base):
    """Individual day within an itinerary."""
    __tablename__ = "itinerary_days"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    itinerary_id = Column(GUID(), ForeignKey("itineraries.id"), nullable=False)
    day_index = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    
    # Relationships
    itinerary = relationship("Itinerary", back_populates="days")
    items = relationship("ItineraryItem", back_populates="day", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_days_itinerary', 'itinerary_id'),
        UniqueConstraint('itinerary_id', 'day_index', name='uq_itinerary_day_index'),
    )


class ItineraryItem(Base):
    """Individual item/activity within a day."""
    __tablename__ = "itinerary_items"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    day_id = Column(GUID(), ForeignKey("itinerary_days.id"), nullable=False)
    item_type = Column(String(20), nullable=False, index=True)
    ref_place_id = Column(GUID(), ForeignKey("places.id"), nullable=True)
    ref_hotel_id = Column(GUID(), ForeignKey("hotels.id"), nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    day = relationship("ItineraryDay", back_populates="items")
    place = relationship("Place", foreign_keys=[ref_place_id])
    hotel = relationship("Hotel", foreign_keys=[ref_hotel_id])
    
    __table_args__ = (
        CheckConstraint("item_type IN ('poi', 'hotel', 'meal', 'transit')", name="check_item_type"),
        Index('idx_items_day', 'day_id'),
        Index('idx_items_type', 'item_type'),
    )


class Place(Base):
    """Points of interest and locations."""
    __tablename__ = "places"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    external_id = Column(String(200), nullable=False)
    name = Column(String(200), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    categories = Column(JSONColumn(), nullable=True)  # Falls back to JSON for SQLite
    rating = Column(Float, nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True, index=True)
    country = Column(String(100), nullable=True, index=True)
    raw_json = Column(JSONColumn(), nullable=True)  # Falls back to JSON for SQLite
    last_synced_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('provider', 'external_id', name='uq_place_provider_external'),
        Index('idx_places_provider_ext', 'provider', 'external_id'),
        Index('idx_places_city_country', 'city', 'country'),
    )


class Hotel(Base):
    """Hotel accommodations."""
    __tablename__ = "hotels"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    external_id = Column(String(200), nullable=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    price_eur_per_night = Column(Float, nullable=True, index=True)
    rating = Column(Float, nullable=True, index=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True, index=True)
    country = Column(String(100), nullable=True, index=True)
    url = Column(Text, nullable=True)
    raw_json = Column(JSONColumn(), nullable=True)  # Falls back to JSON for SQLite
    last_synced_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_hotels_city_price', 'city', 'price_eur_per_night'),
        Index('idx_hotels_rating', 'rating'),
    )


class APICache(Base):
    """Cache for external API responses."""
    __tablename__ = "api_cache"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    endpoint = Column(String(200), nullable=False, index=True)
    params_hash = Column(String(64), nullable=False, unique=True, index=True)
    response_json = Column(JSONColumn(), nullable=False)  # Falls back to JSON for SQLite
    fetched_at = Column(DateTime, nullable=False, default=func.now())
    ttl_seconds = Column(Integer, nullable=False)
    
    __table_args__ = (
        Index('idx_cache_params_hash', 'params_hash'),
        Index('idx_cache_fetched', 'fetched_at'),
    )


class LLMLedger(Base):
    """LLM usage tracking for spend cap enforcement."""
    __tablename__ = "llm_ledger"
    
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id = Column(GUID(), ForeignKey("sessions.id"), nullable=True)
    model = Column(String(50), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    month_key = Column(String(7), nullable=False, index=True)  # YYYY-MM format
    blocked_after = Column(Boolean, nullable=False, default=False)
    
    # Relationships
    session = relationship("Session", foreign_keys=[session_id])
    
    __table_args__ = (
        Index('idx_ledger_month', 'month_key'),
        Index('idx_ledger_session', 'session_id'),
        Index('idx_ledger_created', 'created_at'),
    )