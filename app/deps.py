"""Dependency injection setup for FastAPI."""

import hashlib
from typing import Generator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.base import Base


# Database setup
engine = None
SessionLocal = None


def init_database(settings: Settings) -> None:
    """Initialize database connection."""
    global engine, SessionLocal
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
        echo=settings.debug,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# HTTP Basic Auth for admin
security = HTTPBasic()


def get_admin_user(
    credentials: HTTPBasicCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> str:
    """Authenticate admin user."""
    is_correct_username = credentials.username == settings.admin_username
    is_correct_password = credentials.password == settings.admin_password
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def hash_ip(ip: str, salt: str) -> str:
    """Hash IP address with salt for privacy."""
    return hashlib.sha256(f"{ip}{salt}".encode()).hexdigest()[:16]