from typing import Optional

from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    id: str
    timestamp: str
    agent_id: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details_json: str
    ip_address: Optional[str] = None
    success: int

    model_config = {"from_attributes": True}


class AuditLogQuery(BaseModel):
    agent_id: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
