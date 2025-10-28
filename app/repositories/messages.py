"""Message repository for database operations."""

from typing import List, Optional
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc

from app.db.models import Message


class MessageRepository:
    """Repository for message operations."""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> Message:
        """Create a new message."""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def get_messages_by_session(self, session_id: str) -> List[Message]:
        """Get all messages for a session ordered by creation time."""
        return (
            self.db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at)
            .all()
        )
    
    def get_message(self, message_id: str) -> Optional[Message]:
        """Get message by ID."""
        return self.db.query(Message).filter(Message.id == message_id).first()
    
    def get_recent_messages(self, session_id: str, limit: int = 10) -> List[Message]:
        """Get recent messages for a session."""
        return (
            self.db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
            .all()
        )