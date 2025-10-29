"""Cache repository for API response caching."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session as DBSession

from app.db.models import APICache


class CacheRepository:
    """Repository for API cache operations."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def _hash_params(self, params: Dict[str, Any]) -> str:
        """Create a hash of parameters for cache key.
        Args:
            params (Dict[str, Any]): Parameters dictionary.
        Returns:
            str: SHA256 hash of the parameters.
        """
        params_str = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(params_str.encode()).hexdigest()
    
    def get_cached_response(
        self, provider: str, endpoint: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get cached response if still valid.
        Args:
            provider (str): Data provider name.
            endpoint (str): API endpoint.
            params (Dict[str, Any]): Parameters dictionary.
        Returns:
            Optional[Dict[str, Any]]: Cached response JSON or None if not found/expired
        """
        params_hash = self._hash_params(params)
        
        cache_entry = (
            self.db.query(APICache)
            .filter(
                APICache.provider == provider,
                APICache.endpoint == endpoint,
                APICache.params_hash == params_hash,
            )
            .first()
        )
        
        if cache_entry:
            # Check if cache is still valid
            expires_at = cache_entry.fetched_at + timedelta(seconds=cache_entry.ttl_seconds)
            if datetime.utcnow() <= expires_at:
                return cache_entry.response_json
            else:
                # Remove expired cache
                self.db.delete(cache_entry)
                self.db.commit()
        
        return None
    
    def cache_response(self,
                        provider: str,
                        endpoint: str,
                        params: Dict[str, Any],
                        response: Dict[str, Any],
                        ttl_seconds: int,
                    ) -> APICache:
        """Cache an API response.
        Args:
            provider (str): Data provider name.
            endpoint (str): API endpoint.
            params (Dict[str, Any]): Parameters dictionary.
            response (Dict[str, Any]): Response data to cache.
            ttl_seconds (int): Time-to-live for the cache entry.
        Returns:
            APICache: Created or updated cache entry.
        """
        params_hash = self._hash_params(params)
        
        try:
            # Try to update existing entry first
            existing = (
                self.db.query(APICache)
                .filter(
                    APICache.provider == provider,
                    APICache.endpoint == endpoint,
                    APICache.params_hash == params_hash,
                )
                .first()
            )
            
            if existing:
                # Update existing entry
                existing.response_json = response
                existing.fetched_at = datetime.utcnow()
                existing.ttl_seconds = ttl_seconds
                self.db.commit()
                self.db.refresh(existing)
                return existing
            else:
                # Create new cache entry
                cache_entry = APICache(
                    provider=provider,
                    endpoint=endpoint,
                    params_hash=params_hash,
                    response_json=response,
                    ttl_seconds=ttl_seconds,
                )
                
                self.db.add(cache_entry)
                self.db.commit()
                self.db.refresh(cache_entry)
                return cache_entry
                
        except Exception as e:
            # If there's a constraint error, rollback and try to get existing entry
            self.db.rollback()
            
            existing = (
                self.db.query(APICache)
                .filter(
                    APICache.provider == provider,
                    APICache.endpoint == endpoint,
                    APICache.params_hash == params_hash,
                )
                .first()
            )
            
            if existing:
                # Update the existing entry
                existing.response_json = response
                existing.fetched_at = datetime.utcnow()
                existing.ttl_seconds = ttl_seconds
                self.db.commit()
                self.db.refresh(existing)
                return existing
            else:
                # Re-raise the error if we can't resolve it
                raise e
    
    def clear_expired_cache(self) -> int:
        """Clear all expired cache entries. Returns number of entries cleared.
        Args:
            None
        Returns:
            int: Number of expired cache entries removed.
        """
        now = datetime.utcnow()
        expired_entries = (
            self.db.query(APICache)
            .filter(
                APICache.fetched_at + 
                (APICache.ttl_seconds * timedelta(seconds=1)) < now
            )
            .all()
        )
        
        count = len(expired_entries)
        for entry in expired_entries:
            self.db.delete(entry)
        
        self.db.commit()
        return count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        Args:
            None
        Returns:
            Dict[str, Any]: Cache statistics including total entries and breakdown by provider.
        """
        total_entries = self.db.query(APICache).count()
        
        # Get stats by provider
        provider_stats = {}
        providers = self.db.query(APICache.provider).distinct().all()
        
        for (provider,) in providers:
            provider_count = (
                self.db.query(APICache)
                .filter(APICache.provider == provider)
                .count()
            )
            provider_stats[provider] = provider_count
        
        return {
            "total_entries": total_entries,
            "by_provider": provider_stats,
        }