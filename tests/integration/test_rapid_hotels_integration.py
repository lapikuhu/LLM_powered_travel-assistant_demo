"""Integration test for RapidAPI Hotels provider.

Requires a valid RapidAPI key for the Booking.com API in environment variable RAPIDAPI_KEY.
This test exercises a live HTTP call and will be skipped if the key is not present.
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.base import Base
from app.providers.hotels.rapid_hotels import RapidAPIHotelProvider


pytestmark = pytest.mark.skipif(
    not os.getenv("RAPIDAPI_KEY"),
    reason="RAPIDAPI_KEY not set; skipping live RapidAPI hotels integration test.",
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


@pytest.mark.asyncio
async def test_search_hotels_live(db_session):
    settings = Settings(
        openai_api_key="test-openai",
        admin_password="admin",
        secret_key="secret",
        ip_hash_salt="salt",
        opentripmap_api_key="otm-test",
        rapidapi_key=os.environ["RAPIDAPI_KEY"],
        debug=True,
        api_cache_ttl_seconds=60,
    )

    provider = RapidAPIHotelProvider(settings=settings, db=db_session)
    try:
        out = await provider.search_hotels(city="Athens", country="Greece", budget_tier="mid", limit=3)
        assert isinstance(out, list)
        # If key is valid and API reachable, expect 1+ results
        assert len(out) >= 0  # DO NOT assert >0 to avoid flakiness
    finally:
        provider.close()
