"""Optional integration test against the real OpenTripMap API.

This test is skipped unless the environment variable OPENTRIPMAP_API_KEY is set.
Run with:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_asyncio.plugin -m "not slow"
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.base import Base
from app.providers.opentripmap_client import OpenTripMapClient


has_key = bool(os.getenv("OPENTRIPMAP_API_KEY"))


@pytest.mark.asyncio
@pytest.mark.skipif(not has_key, reason="OPENTRIPMAP_API_KEY not set; skipping live API test")
async def test_live_radius_returns_pois():
    # Prepare DB
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Settings with real key from env
        settings = Settings(
            openai_api_key="stub",
            admin_password="admin",
            secret_key="secret",
            ip_hash_salt="salt",
            opentripmap_api_key=os.environ["OPENTRIPMAP_API_KEY"],
            debug=False,
        )

        client = OpenTripMapClient(settings=settings, db=db)

        # Central Athens
        results = await client.search_places_by_radius(lat=37.9838, lon=23.7275, radius=1500, kinds="interesting_places", limit=20)

        # We expect at least a few POIs
        assert isinstance(results, list)
        assert len(results) > 0

        client.close()
    finally:
        db.close()
