from pydantic import BaseModel, Field


class CapabilityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="")


class CapabilityResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str

    model_config = {"from_attributes": True}


class GrantRequest(BaseModel):
    capability_id: str
