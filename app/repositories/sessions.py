"""Session repository for database operations."""

from typing import Optional
from sqlalchemy.orm import Session as DBSession

from app.db.models import Session
from app.deps import hash_ip


class SessionRepository:
    """Repository for session operations."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create_session(self, ip_address: str, salt: str) -> Session:
        """Create a new session."""
        ip_hashed = hash_ip(ip_address, salt)
        session = Session(ip_hash=ip_hashed)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self.db.query(Session).filter(Session.id == session_id).first()
    
    def get_sessions_by_ip_hash(self, ip_hash: str) -> list[Session]:
        """Get sessions by IP hash."""
        return self.db.query(Session).filter(Session.ip_hash == ip_hash).all()