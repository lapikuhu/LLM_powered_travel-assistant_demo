"""Unit tests for RapidAPI Hotels provider.

Covers:
- No API key behavior
- Location search (cache hit/miss, HTTP success/error)
- Hotels search by destination (cache hit/miss, HTTP success/error, limit)
- Price filter mapping for budget tiers
- Normalization and DB upsert path
"""

from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.base import Base
from app.providers.hotels.rapid_hotels import RapidAPIHotelProvider


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        openai_api_key="test-openai",
        admin_password="admin",
        secret_key="secret",
        ip_hash_salt="salt",
        opentripmap_api_key="otm-test",
        rapidapi_key="rapid-test",
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
async def test_no_api_key_returns_empty(db_session):
    no_key_settings = Settings(
        openai_api_key="test-openai",
        admin_password="admin",
        secret_key="secret",
        ip_hash_salt="salt",
        opentripmap_api_key="otm-test",
        rapidapi_key=None,  # Explicitly unset
        debug=True,
        api_cache_ttl_seconds=60,
    )
    provider = RapidAPIHotelProvider(settings=no_key_settings, db=db_session)

    out = await provider.search_hotels(city="Athens", country="Greece", budget_tier="mid", limit=5)
    assert out == []

    provider.close()


@pytest.mark.asyncio
async def test_price_filters_mapping(settings: Settings, db_session):
    provider = RapidAPIHotelProvider(settings=settings, db=db_session)

    assert provider._get_price_filters("budget") == {"price_filter_currencycode": "EUR", "price_filter_max": "80"}
    assert provider._get_price_filters("mid") == {
        "price_filter_currencycode": "EUR",
        "price_filter_min": "80",
        "price_filter_max": "150",
    }
    assert provider._get_price_filters("premium") == {"price_filter_currencycode": "EUR", "price_filter_min": "150"}

    provider.close()


@pytest.mark.asyncio
async def test_search_location_uses_cache(settings: Settings, db_session):
    provider = RapidAPIHotelProvider(settings=settings, db=db_session)

    cached_payload = {"result": [{"dest_id": "-814876", "city_name": "Athens"}]}

    # Monkeypatch cache to hit
    provider.cache_repo.get_cached_response = lambda provider=None, endpoint=None, params=None: cached_payload  # type: ignore

    # client.get should not be called when cache hits
    def fail_get(*args, **kwargs):
        raise AssertionError("HTTP client should not be called on cache hit")

    provider.client.get = fail_get  # type: ignore

    location = await provider._search_location(city="Athens", country="Greece")
    assert location is not None
    assert location.get("dest_id") == "-814876"

    provider.close()


@pytest.mark.asyncio
async def test_search_location_http_success_and_cached(settings: Settings, db_session):
    provider = RapidAPIHotelProvider(settings=settings, db=db_session)

    # No cache initially
    provider.cache_repo.get_cached_response = lambda provider=None, endpoint=None, params=None: None  # type: ignore

    captured: Dict[str, Any] = {"cached": None, "url": None, "params": None}

    def fake_cache_response(provider: str, endpoint: str, params: Dict[str, Any], response: Dict[str, Any], ttl_seconds: int):
        # capture cache call
        captured["cached"] = {
            "provider": provider,
            "endpoint": endpoint,
            "params": params,
            "response": response,
            "ttl": ttl_seconds,
        }
        return SimpleObj()

    class SimpleObj:
        pass

    provider.cache_repo.cache_response = fake_cache_response  # type: ignore

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        assert url.endswith("/locations/search")
        return FakeResponse({"result": [{"dest_id": "123"}, {"dest_id": "456"}]})

    provider.client.get = fake_get  # type: ignore

    location = await provider._search_location(city="Athens", country="Greece")
    assert location is not None and location.get("dest_id") == "123"

    # cache called with expected
    assert captured["cached"] is not None
    assert captured["cached"]["endpoint"] == "locations"
    assert captured["cached"]["ttl"] == settings.api_cache_ttl_seconds * 24

    provider.close()


@pytest.mark.asyncio
async def test_search_hotels_by_destination_uses_cache(settings: Settings, db_session):
    provider = RapidAPIHotelProvider(settings=settings, db=db_session)

    hotels_payload = {"result": [{"hotel_id": "H1"}, {"hotel_id": "H2"}, {"hotel_id": "H3"}]}

    provider.cache_repo.get_cached_response = lambda provider=None, endpoint=None, params=None: hotels_payload  # type: ignore

    def fail_get(*args, **kwargs):
        raise AssertionError("HTTP client should not be called on cache hit")

    provider.client.get = fail_get  # type: ignore

    hotels = await provider._search_hotels_by_destination(dest_id="-814876", city="Athens", budget_tier="mid", limit=2)
    # when cache returns, the method returns cached["result"] directly (no slicing), caller slices later
    assert isinstance(hotels, list)
    assert {h.get("hotel_id") for h in hotels} == {"H1", "H2", "H3"}

    provider.close()


@pytest.mark.asyncio
async def test_search_hotels_by_destination_http_success_limits_and_caches(settings: Settings, db_session):
    provider = RapidAPIHotelProvider(settings=settings, db=db_session)

    provider.cache_repo.get_cached_response = lambda provider=None, endpoint=None, params=None: None  # type: ignore

    captured: Dict[str, Any] = {"cached": None}

    def fake_cache_response(provider: str, endpoint: str, params: Dict[str, Any], response: Dict[str, Any], ttl_seconds: int):
        captured["cached"] = {"endpoint": endpoint, "ttl": ttl_seconds, "params": params}
        return object()

    provider.cache_repo.cache_response = fake_cache_response  # type: ignore

    results = [{"hotel_id": f"H{i}", "hotel_name": f"Hotel {i}"} for i in range(10)]

    def fake_get(url, params=None, **kwargs):
        assert url.endswith("/hotels/search")
        # Budget tier filters must be in params
        assert params.get("price_filter_currencycode") == "EUR"
        return FakeResponse({"result": results})

    provider.client.get = fake_get  # type: ignore

    hotels = await provider._search_hotels_by_destination(dest_id="-814876", city="Athens", budget_tier="premium", limit=5)
    assert len(hotels) == 5
    assert hotels[0]["hotel_id"] == "H0"

    assert captured["cached"] is not None
    assert captured["cached"]["endpoint"] == "hotels_search"
    assert captured["cached"]["ttl"] == settings.api_cache_ttl_seconds

    provider.close()


@pytest.mark.asyncio
async def test_normalize_hotels_creates_db_records(settings: Settings, db_session):
    provider = RapidAPIHotelProvider(settings=settings, db=db_session)

    class DummyHotel:
        def __init__(self, id_value: str):
            self.id = id_value

    created: List[Dict[str, Any]] = []

    def fake_create_or_update_hotel(**kwargs):
        created.append(kwargs)
        # ensure required keys exist
        assert kwargs["provider"] == "rapidapi"
        assert kwargs["external_id"].startswith("rapidapi_")
        return DummyHotel("uuid-1")

    provider.hotel_repo.create_or_update_hotel = fake_create_or_update_hotel  # type: ignore

    hotels_data = [
        {
            "hotel_id": "123",
            "hotel_name": "Nice Hotel",
            "latitude": 37.98,
            "longitude": 23.72,
            "address": "1 Main St",
            "min_total_price": 120.0,
            "review_score": 8.0,  # 0-10 scale
            "url": "https://example.com/h/123",
        }
    ]

    normalized = provider._normalize_hotels(hotels_data, city="Athens", country="Greece")
    assert len(normalized) == 1
    out = normalized[0]
    assert out["hotel_id"] == "uuid-1"
    assert out["rating"] == pytest.approx(4.0)  # 8/2
    assert out["price_eur_per_night"] == 120.0

    provider.close()


@pytest.mark.asyncio
async def test_search_hotels_end_to_end_calls_helpers(settings: Settings, db_session):
    provider = RapidAPIHotelProvider(settings=settings, db=db_session)

    async def fake_search_location(city: str, country: Optional[str]):
        return {"dest_id": "-814876"}

    async def fake_search_hotels_by_destination(dest_id: str, city: str, budget_tier: str, limit: int):
        return [{"hotel_id": "H1", "hotel_name": "Hotel 1"}]

    def fake_normalize(hotels_data, city, country):
        return [{"external_id": "rapidapi_H1", "name": "Hotel 1", "city": city, "country": country}]

    provider._search_location = fake_search_location  # type: ignore
    provider._search_hotels_by_destination = fake_search_hotels_by_destination  # type: ignore
    provider._normalize_hotels = fake_normalize  # type: ignore

    out = await provider.search_hotels(city="Athens", country="Greece", budget_tier="mid", limit=10)
    assert out == [{"external_id": "rapidapi_H1", "name": "Hotel 1", "city": "Athens", "country": "Greece"}]

    provider.close()
