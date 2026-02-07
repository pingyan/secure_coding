import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text

from database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    agent_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    details_json = Column(Text, default="{}")
    ip_address = Column(String, nullable=True)
    success = Column(Integer, default=1)
