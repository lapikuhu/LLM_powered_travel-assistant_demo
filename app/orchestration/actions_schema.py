"""Tool action schema definitions for LLM orchestrator."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class SearchPOIsAction(BaseModel):
    """Action to search for points of interest."""
    action: str = Field(default="search_pois", description="Action type")
    city: str = Field(description="City name to search in")
    country: Optional[str] = Field(default=None, description="Country name for better matching")
    categories: Optional[List[str]] = Field(
        default=None,
        description="POI categories (e.g., museums, restaurants, historic)"
    )
    limit: Optional[int] = Field(default=20, description="Maximum number of POIs to return")


class SearchHotelsAction(BaseModel):
    """Action to search for hotels."""
    action: str = Field(default="search_hotels", description="Action type")
    city: str = Field(description="City name to search in")
    country: Optional[str] = Field(default=None, description="Country name for better matching")
    budget_tier: str = Field(
        default="mid",
        description="Budget tier: 'budget', 'mid', or 'premium'"
    )
    limit: Optional[int] = Field(default=10, description="Maximum number of hotels to return")


class FinalizeItineraryAction(BaseModel):
    """Action to finalize and save the itinerary."""
    action: str = Field(default="finalize_itinerary", description="Action type")
    city: str = Field(description="Destination city")
    country: Optional[str] = Field(default=None, description="Destination country")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: str = Field(description="End date in YYYY-MM-DD format")
    budget_tier: str = Field(description="Budget tier: 'budget', 'mid', or 'premium'")
    days: List[Dict[str, Any]] = Field(description="List of day objects with activities")


class ActionResult(BaseModel):
    """Result of an action execution."""
    action: str = Field(description="Action type that was executed")
    success: bool = Field(description="Whether the action succeeded")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Result data")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# Tool schema for OpenAI function calling
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "execute_travel_action",
        "description": "Execute travel planning actions like searching POIs, hotels, or finalizing itinerary",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search_pois", "search_hotels", "finalize_itinerary"],
                    "description": "The action to execute"
                },
                "city": {
                    "type": "string",
                    "description": "City name"
                },
                "country": {
                    "type": "string",
                    "description": "Country name (optional)"
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "POI categories for search_pois action"
                },
                "budget_tier": {
                    "type": "string",
                    "enum": ["budget", "mid", "premium"],
                    "description": "Budget tier for hotels or itinerary"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return"
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format for finalize_itinerary"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format for finalize_itinerary"
                },
                "days": {
                    "type": "array",
                    "description": "Array of day objects for finalize_itinerary",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_index": {"type": "integer"},
                            "date": {"type": "string"},
                            "activities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["poi", "hotel", "meal", "transit"]
                                        },
                                        "name": {"type": "string"},
                                        "external_id": {"type": "string"},
                                        "start_time": {"type": "string"},
                                        "end_time": {"type": "string"},
                                        "notes": {"type": "string"}
                                    },
                                    "required": ["type", "name"]
                                }
                            }
                        },
                        "required": ["day_index", "date", "activities"]
                    }
                }
            },
            "required": ["action", "city"],
            "additionalProperties": False
        }
    }
}