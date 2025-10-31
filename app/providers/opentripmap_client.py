"""OpenTripMap API client with caching and normalization."""

import logging
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.orm import Session as DBSession

from app.config import Settings
from app.repositories.cache import CacheRepository
from app.repositories.places import PlaceRepository

logger = logging.getLogger(__name__)


class OpenTripMapClient:
    """Client for OpenTripMap POI API with caching."""
    
    def __init__(self, settings: Settings, db: DBSession):
        self.api_key = settings.opentripmap_api_key
        self.base_url = "https://api.opentripmap.com/0.1/en/places"
        self.cache_ttl = settings.api_cache_ttl_seconds
        self.cache_repo = CacheRepository(db)
        self.places_repo = PlaceRepository(db)
        
        # HTTP client with timeout
        self.client = httpx.Client(timeout=30.0)
    
    async def search_places_by_bbox(self,
                                    bbox: str,  # "lon_min,lat_min,lon_max,lat_max"
                                    kinds: Optional[str] = None,
                                    limit: int = 50,
                                ) -> List[Dict[str, Any]]:
        """Search places within bounding box.
        Args:
            bbox (str): Bounding box in "lon_min,lat_min,lon_max,lat_max" format.
            kinds (Optional[str]): Comma-separated kinds/categories to filter.
            limit (int): Maximum number of results to return.
        Returns:
            List[Dict[str, Any]]: List of normalized place data.
        """
        params = {
            "apikey": self.api_key,
            "bbox": bbox,
            "limit": limit,
            # Use GeoJSON so response has a FeatureCollection with `features`
            "format": "geojson",
        }
        
        if kinds:
            params["kinds"] = kinds
        
        # Check cache first
        cached = self.cache_repo.get_cached_response(
            provider="opentripmap",
            endpoint="bbox_search",
            params=params
        )
        
        if cached:
            logger.info(f"Cache hit for bbox search: {bbox}")
            return self._normalize_search_response(cached)
        
        # Make API call
        try:
            url = f"{self.base_url}/bbox"
            response = self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Try to cache the response, but don't fail if caching fails
            try:
                self.cache_repo.cache_response(
                    provider="opentripmap",
                    endpoint="bbox_search",
                    params=params,
                    response=data,
                    ttl_seconds=self.cache_ttl,
                )
            except Exception as cache_error:
                logger.warning(f"Failed to cache OpenTripMap response: {cache_error}")
                # Continue processing even if caching fails
            
            normalized = self._normalize_search_response(data)
            logger.info(f"API call successful for bbox: {bbox}, found {len(normalized)} places")
            return normalized
            
        except httpx.HTTPError as e:
            logger.error(f"OpenTripMap API error for bbox {bbox}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in OpenTripMap bbox search: {e}")
            return []
    
    async def search_places_by_radius(self,
                                    lat: float,
                                    lon: float,
                                    radius: int = 5000,  # meters
                                    kinds: Optional[str] = None,
                                    limit: int = 50,
                                ) -> List[Dict[str, Any]]:
        """Search places within radius of coordinates.
        Args:
            lat (float): Latitude of center point.
            lon (float): Longitude of center point.
            radius (int): Search radius in meters.
            kinds (Optional[str]): Comma-separated kinds/categories to filter.
            limit (int): Maximum number of results to return.
        Returns:
            List[Dict[str, Any]]: List of normalized place data.
        """
        params = {
            "apikey": self.api_key,
            "lat": lat,
            "lon": lon,
            "radius": radius,
            "limit": limit,
            # Use GeoJSON so response has a FeatureCollection with `features`
            "format": "geojson",
        }
        
        if kinds:
            params["kinds"] = kinds
        
        # Check cache first
        cached = self.cache_repo.get_cached_response(
            provider="opentripmap",
            endpoint="radius_search",
            params=params
        )
        
        if cached:
            logger.info(f"Cache hit for radius search: {lat},{lon}")
            return self._normalize_search_response(cached)
        
        # Make API call
        try:
            url = f"{self.base_url}/radius"
            response = self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Try to cache the response, but don't fail if caching fails
            try:
                self.cache_repo.cache_response(
                    provider="opentripmap",
                    endpoint="radius_search",
                    params=params,
                    response=data,
                    ttl_seconds=self.cache_ttl,
                )
            except Exception as cache_error:
                logger.warning(f"Failed to cache OpenTripMap response: {cache_error}")
                # Continue processing even if caching fails
            
            normalized = self._normalize_search_response(data)
            # If geojson returned 0 places, try a fallback call using JSON format
            if not normalized:
                try:
                    fallback_params = dict(params)
                    fallback_params["format"] = "json"
                    fallback_response = self.client.get(url, params=fallback_params)
                    fallback_response.raise_for_status()
                    fallback_data = fallback_response.json()
                    normalized = self._normalize_search_response(fallback_data)
                    if normalized:
                        # Best-effort cache the fallback response too
                        try:
                            self.cache_repo.cache_response(
                                provider="opentripmap",
                                endpoint="radius_search",
                                params=fallback_params,
                                response=fallback_data,
                                ttl_seconds=self.cache_ttl,
                            )
                        except Exception:
                            pass
                except Exception as fallback_err:
                    logger.info(f"OpenTripMap JSON fallback yielded no results or failed: {fallback_err}")

            logger.info(f"API call successful for radius: {lat},{lon}, found {len(normalized)} places")
            return normalized
            
        except httpx.HTTPError as e:
            logger.error(f"OpenTripMap API error for radius {lat},{lon}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in OpenTripMap radius search: {e}")
            return []
    
    async def get_place_details(self, xid: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific place.
        Args:
            xid (str): External ID of the place.
        Returns:
            Optional[Dict[str, Any]]: Normalized place detail data or None if not found.
        """
        params = {
            "apikey": self.api_key,
        }
        
        # Check cache first
        cached = self.cache_repo.get_cached_response(
            provider="opentripmap",
            endpoint="place_details",
            params={"xid": xid, **params}
        )
        
        if cached:
            logger.info(f"Cache hit for place details: {xid}")
            return self._normalize_place_detail(cached)
        
        # Make API call
        try:
            url = f"{self.base_url}/xid/{xid}"
            response = self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Try to cache the response, but don't fail if caching fails
            try:
                self.cache_repo.cache_response(
                    provider="opentripmap",
                    endpoint="place_details",
                    params={"xid": xid, **params},
                    response=data,
                    ttl_seconds=self.cache_ttl,
                )
            except Exception as cache_error:
                logger.warning(f"Failed to cache OpenTripMap response: {cache_error}")
                # Continue processing even if caching fails
            
            logger.info(f"API call successful for place details: {xid}")
            return self._normalize_place_detail(data)
            
        except httpx.HTTPError as e:
            logger.error(f"OpenTripMap API error for place {xid}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting place details for {xid}: {e}")
            return None
    
    def _normalize_places(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize place data from API response.
        Args:
            features (List[Dict[str, Any]]): List of place features from API.
        Returns:
            List[Dict[str, Any]]: List of normalized place data.
        """
        normalized = []
        
        for feature in features:
            try:
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                coordinates = geometry.get("coordinates", [0, 0])
                
                normalized_place = {
                    "external_id": properties.get("xid", ""),
                    "name": properties.get("name", "Unnamed Place"),
                    "lat": coordinates[1] if len(coordinates) > 1 else 0,
                    "lon": coordinates[0] if len(coordinates) > 0 else 0,
                    "categories": self._parse_kinds(properties.get("kinds", "")),
                    "rating": properties.get("rate", None),
                    "address": None,  # Not available in basic search
                    "city": None,     # Will be inferred
                    "country": None,  # Will be inferred
                    "raw_json": feature,
                }
                
                # Store in database for caching
                if normalized_place["external_id"]:
                    place = self.places_repo.create_or_update_place(
                        provider="opentripmap",
                        **normalized_place
                    )
                    normalized_place["place_id"] = str(place.id)
                
                normalized.append(normalized_place)
                
            except Exception as e:
                logger.warning(f"Error normalizing place: {e}")
                continue
        
        return normalized

    def _normalize_search_response(self, data: Any) -> List[Dict[str, Any]]:
        """Normalize either GeoJSON FeatureCollection or JSON list response.
        Args:
            data (Any): API response JSON.
        Returns:
            List[Dict[str, Any]]: Normalized places.
        """
        try:
            # GeoJSON FeatureCollection
            if isinstance(data, dict) and isinstance(data.get("features"), list):
                return self._normalize_places(data.get("features", []))

            # Plain JSON list (each item contains at least xid, name, point{lat,lon})
            if isinstance(data, list):
                pseudo_features: List[Dict[str, Any]] = []
                for item in data:
                    lon = item.get("point", {}).get("lon") if isinstance(item.get("point"), dict) else None
                    lat = item.get("point", {}).get("lat") if isinstance(item.get("point"), dict) else None
                    # Build a GeoJSON-like feature for reuse of the same normalizer
                    feature = {
                        "type": "Feature",
                        "properties": item,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [lon or 0, lat or 0],
                        },
                    }
                    pseudo_features.append(feature)
                return self._normalize_places(pseudo_features)
        except Exception as e:
            logger.warning(f"Failed to normalize search response: {e}")
            return []

        return []
    
    def _normalize_place_detail(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize detailed place data.
        Args:
            data (Dict[str, Any]): Place detail data from API.
        Returns:
            Optional[Dict[str, Any]]: Normalized place detail data or None on error.
        """
        try:
            # Extract coordinates from point geometry
            coordinates = [0, 0]
            if "point" in data:
                coordinates = [
                    data["point"].get("lon", 0),
                    data["point"].get("lat", 0)
                ]
            
            # Extract address information
            address_info = data.get("address", {})
            
            normalized = {
                "external_id": data.get("xid", ""),
                "name": data.get("name", "Unnamed Place"),
                "lat": coordinates[1],
                "lon": coordinates[0],
                "categories": self._parse_kinds(data.get("kinds", "")),
                "rating": data.get("rate", None),
                "address": self._format_address(address_info),
                "city": address_info.get("city"),
                "country": address_info.get("country"),
                "raw_json": data,
            }
            
            # Store/update in database
            if normalized["external_id"]:
                place = self.places_repo.create_or_update_place(
                    provider="opentripmap",
                    **normalized
                )
                normalized["place_id"] = str(place.id)
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing place detail: {e}")
            return None
    
    def _parse_kinds(self, kinds_string: str) -> List[str]:
        """Parse kinds string into category list.
        Args:
            kinds_string (str): Comma-separated kinds string.
        Returns:
            List[str]: List of category strings.
        """
        if not kinds_string:
            return []
        return [kind.strip() for kind in kinds_string.split(",") if kind.strip()]
    
    def _format_address(self, address_info: Dict[str, Any]) -> Optional[str]:
        """Format address from address components.
        Args:
            address_info (Dict[str, Any]): Address components.
        Returns:
            Optional[str]: Formatted address string or None if empty.
        """
        if not address_info:
            return None
        
        components = []
        for field in ["house_number", "road", "city", "country"]:
            value = address_info.get(field)
            if value:
                components.append(str(value))
        
        return ", ".join(components) if components else None
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except Exception:
            pass  # Ignore errors during cleanup