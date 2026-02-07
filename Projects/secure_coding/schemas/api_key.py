from typing import Optional

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(default="default", max_length=128)
    expires_at: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: str
    agent_id: str
    key_prefix: str
    name: str
    status: str
    expires_at: Optional[str] = None
    created_at: str
    rotated_at: Optional[str] = None
    revoked_at: Optional[str] = None
    last_used_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(BaseModel):
    id: str
    agent_id: str
    key_prefix: str
    name: str
    raw_key: str
    status: str
    expires_at: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class KeyRotationResponse(BaseModel):
    old_key_id: str
    new_key: ApiKeyCreatedResponse
    grace_period_hours: int
