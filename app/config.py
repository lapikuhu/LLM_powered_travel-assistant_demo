"""Configuration management for Travel Assistant Chatbot."""

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = "sqlite:///./travel_assistant.db"
    
    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4"
    monthly_spend_cap_usd: float = 10.0
    
    # OpenTripMap
    opentripmap_api_key: str
    
    # RapidAPI Hotels (optional)
    rapidapi_key: Optional[str] = None
    rapidapi_hotels_enabled: bool = False
    
    # Admin credentials
    admin_username: str = "admin"
    admin_password: str
    
    # Security
    secret_key: str
    ip_hash_salt: str
    
    # Rate limiting
    rate_limit_per_day: int = 30
    
    # Cache settings
    api_cache_ttl_seconds: int = 3600  # 1 hour
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()