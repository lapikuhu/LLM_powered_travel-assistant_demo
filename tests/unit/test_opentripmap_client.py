"""Unit tests for OpenTripMap client.

Covers:
- Correct request parameters (expects GeoJSON format)
- Normalization of bbox/radius search results
- Detail fetching normalization
- Error handling paths
"""

import asyncio
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.base import Base
from app.providers.opentripmap_client import OpenTripMapClient


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        openai_api_key="test-openai",
        admin_password="admin",
        secret_key="secret",
        ip_hash_salt="salt",
        opentripmap_api_key="otm-test",
        debug=True,
        api_cache_ttl_seconds=60,
    )


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class FakeResponse:
    def __init__(self, json_data: Dict[str, Any], status_code: int = 200):
        self._json = json_data
        self.status_code = status_code

    def json(self) -> Dict[str, Any]:
        return self._json

    def raise_for_status(self):
        if not (200 <= self.status_code < 400):
            raise Exception(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_radius_search_uses_geojson_and_normalizes(settings: Settings, db_session):
    client = OpenTripMapClient(settings=settings, db=db_session)

    # Prepare a fake geojson response with two features
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"xid": "X1", "name": "Spot 1", "kinds": "cultural,interesting_places", "rate": 7},
                "geometry": {"type": "Point", "coordinates": [23.7275, 37.9838]},
            },
            {
                "type": "Feature",
                "properties": {"xid": "X2", "name": "Spot 2", "kinds": "historic", "rate": 6},
                "geometry": {"type": "Point", "coordinates": [23.73, 37.98]},
            },
        ],
    }

    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params or {}
        # Assert we request geojson to match normalization path
        assert captured["params"].get("format") == "geojson"
        assert url.endswith("/radius")
        return FakeResponse(geojson)

    # Patch the underlying httpx client
    client.client.get = fake_get  # type: ignore

    places = await client.search_places_by_radius(lat=37.9838, lon=23.7275, radius=1000, kinds="interesting_places", limit=10)

    assert isinstance(places, list)
    assert len(places) == 2
    assert {p["external_id"] for p in places} == {"X1", "X2"}
    assert places[0]["lat"] != 0 and places[0]["lon"] != 0
    # Categories parsed into list
    assert isinstance(places[0]["categories"], list)

    client.close()


@pytest.mark.asyncio
async def test_bbox_search_uses_geojson_and_handles_empty(settings: Settings, db_session):
    client = OpenTripMapClient(settings=settings, db=db_session)

    # Empty feature collection
    geojson = {"type": "FeatureCollection", "features": []}

    def fake_get(url, params=None, **kwargs):
        assert (params or {}).get("format") == "geojson"
        assert url.endswith("/bbox")
        return FakeResponse(geojson)

    client.client.get = fake_get  # type: ignore

    places = await client.search_places_by_bbox(bbox="23.7,37.96,23.8,38.0", kinds=None, limit=5)
    assert places == []

    client.close()


@pytest.mark.asyncio
async def test_get_place_details_normalizes_result(settings: Settings, db_session):
    client = OpenTripMapClient(settings=settings, db=db_session)

    details = {
        "xid": "X123",
        "name": "Acropolis",
        "kinds": "cultural,ancient,interesting_places",
        "rate": 7,
        "point": {"lon": 23.7261, "lat": 37.9715},
        "address": {"house_number": None, "road": "Acropolis", "city": "Athens", "country": "Greece"},
    }

    def fake_get(url, params=None, **kwargs):
        assert url.endswith("/xid/X123")
        return FakeResponse(details)

    client.client.get = fake_get  # type: ignore

    out = await client.get_place_details("X123")
    assert out is not None
    assert out["external_id"] == "X123"
    assert out["city"] == "Athens"
    assert out["country"] == "Greece"
    assert isinstance(out["categories"], list)

    client.close()


@pytest.mark.asyncio
async def test_http_error_returns_empty_structures(settings: Settings, db_session):
    client = OpenTripMapClient(settings=settings, db=db_session)

    class ErrorResponse:
        def raise_for_status(self):
            raise Exception("HTTP 500")

        def json(self):
            return {}

    def fake_get_error(url, params=None, **kwargs):
        return ErrorResponse()

    client.client.get = fake_get_error  # type: ignore

    places = await client.search_places_by_radius(lat=0, lon=0)
    assert places == []

    detail = await client.get_place_details("XERR")
    assert detail is None

    client.close()
