import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    key_prefix = Column(String(8), nullable=False)
    key_hash = Column(String(64), nullable=False)
    name = Column(String, default="default")
    status = Column(String, nullable=False, default="active")
    expires_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    rotated_at = Column(String, nullable=True)
    revoked_at = Column(String, nullable=True)
    last_used_at = Column(String, nullable=True)

    agent = relationship("Agent", back_populates="api_keys")
