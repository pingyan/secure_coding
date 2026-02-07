import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class Capability(Base):
    __tablename__ = "capabilities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    created_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

    agent_capabilities = relationship("AgentCapability", back_populates="capability", cascade="all, delete-orphan")


class AgentCapability(Base):
    __tablename__ = "agent_capabilities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    capability_id = Column(String, ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False)
    granted_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    granted_by = Column(String, nullable=True)

    __table_args__ = (UniqueConstraint("agent_id", "capability_id", name="uq_agent_capability"),)

    agent = relationship("Agent", back_populates="agent_capabilities")
    capability = relationship("Capability", back_populates="agent_capabilities")
