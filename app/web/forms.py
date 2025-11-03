"""Pydantic models for form validation."""

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, validator


class ChatForm(BaseModel):
    """Form for chat messages."""
    message: str = Field(..., min_length=1, max_length=1000, description="Chat message")
    # Split destination into structured fields
    city: Optional[str] = Field(None, max_length=100, description="Destination city")
    country: Optional[str] = Field(None, max_length=100, description="Destination country")
    start_date: Optional[date] = Field(None, description="Start date")
    end_date: Optional[date] = Field(None, description="End date")
    budget_tier: Optional[str] = Field(None, description="Budget tier")
    
    @validator('budget_tier')
    def validate_budget_tier(cls, v):
        """Validate budget tier value."""
        if v is not None and v not in ['budget', 'mid', 'premium']:
            raise ValueError('Budget tier must be budget, mid, or premium')
        return v
    
    @validator('end_date')
    def validate_dates(cls, v, values):
        """Validate that end date is after start date."""
        if v is not None and 'start_date' in values and values['start_date'] is not None:
            if v <= values['start_date']:
                raise ValueError('End date must be after start date')
        return v