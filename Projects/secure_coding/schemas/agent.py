import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

AGENT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
VALID_STATUSES = {"active", "suspended", "revoked"}
VALID_AGENT_TYPES = {"llm", "tool", "orchestrator", "custom"}


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="")
    owner: str = Field(..., min_length=1, max_length=128)
    agent_type: str = Field(default="custom")
    metadata_json: str = Field(default="{}")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not AGENT_NAME_PATTERN.match(v):
            raise ValueError("Name must match ^[a-zA-Z0-9_-]+$")
        return v

    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v: str) -> str:
        if v not in VALID_AGENT_TYPES:
            raise ValueError(f"agent_type must be one of {VALID_AGENT_TYPES}")
        return v


class AgentUpdate(BaseModel):
    description: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=128)
    agent_type: Optional[str] = None
    metadata_json: Optional[str] = None

    @field_validator("agent_type")
    @classmethod
    def validate_agent_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_AGENT_TYPES:
            raise ValueError(f"agent_type must be one of {VALID_AGENT_TYPES}")
        return v


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    owner: str
    status: str
    agent_type: str
    metadata_json: str
    created_at: str
    updated_at: str
    suspended_at: Optional[str] = None
    revoked_at: Optional[str] = None

    model_config = {"from_attributes": True}


class SuspendRequest(BaseModel):
    reason: str = Field(default="No reason provided", max_length=500)


class RevokeRequest(BaseModel):
    reason: str = Field(default="No reason provided", max_length=500)
