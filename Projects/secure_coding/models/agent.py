import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, default="")
    owner = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    agent_type = Column(String, nullable=False, default="custom")
    metadata_json = Column(Text, default="{}")
    created_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    suspended_at = Column(String, nullable=True)
    revoked_at = Column(String, nullable=True)

    api_keys = relationship("ApiKey", back_populates="agent", cascade="all, delete-orphan")
    agent_capabilities = relationship("AgentCapability", back_populates="agent", cascade="all, delete-orphan")
