"""Main FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.deps import init_database
from app.web.routes import router


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    
    # Initialize database
    init_database(settings)
    logger.info("Database initialized")
    
    yield
    
    # Cleanup if needed
    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="Travel Assistant Chatbot",
        description="A simple city-trip itinerary generator via chat",
        version="1.0.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    
    # Include routes
    app.include_router(router)
    
    # Mount static files
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )