from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth.audit_helper import log_audit_event
from auth.dependencies import require_capability
from database import get_db
from models.agent import Agent
from models.capability import AgentCapability, Capability
from schemas.capability import CapabilityCreate, CapabilityResponse, GrantRequest

router = APIRouter(tags=["capabilities"])


@router.post("/capabilities", response_model=CapabilityResponse, status_code=status.HTTP_201_CREATED)
async def create_capability(
    body: CapabilityCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("admin:*")),
):
    existing = db.query(Capability).filter(Capability.name == body.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Capability already exists")

    cap = Capability(name=body.name, description=body.description)
    db.add(cap)
    db.commit()
    db.refresh(cap)

    log_audit_event(
        db,
        action="capability.created",
        agent_id=current_agent["agent_id"],
        resource_type="capability",
        resource_id=cap.id,
        details={"name": cap.name},
        ip_address=request.client.host if request.client else None,
    )

    return cap


@router.get("/capabilities", response_model=list[CapabilityResponse])
async def list_capabilities(
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("agents:read")),
):
    return db.query(Capability).all()


@router.post(
    "/agents/{agent_id}/capabilities",
    response_model=CapabilityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_capability(
    agent_id: str,
    body: GrantRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("admin:*")),
):
    # No self-elevation
    if agent_id == current_agent["agent_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify your own capabilities"
        )

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    cap = db.query(Capability).filter(Capability.id == body.capability_id).first()
    if not cap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found")

    existing = (
        db.query(AgentCapability)
        .filter(AgentCapability.agent_id == agent_id, AgentCapability.capability_id == cap.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Capability already granted")

    grant = AgentCapability(
        agent_id=agent_id,
        capability_id=cap.id,
        granted_by=current_agent["agent_id"],
    )
    db.add(grant)
    db.commit()

    log_audit_event(
        db,
        action="capability.granted",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent_id,
        details={"capability": cap.name, "capability_id": cap.id},
        ip_address=request.client.host if request.client else None,
    )

    return cap


@router.delete("/agents/{agent_id}/capabilities/{cap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_capability(
    agent_id: str,
    cap_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("admin:*")),
):
    if agent_id == current_agent["agent_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify your own capabilities"
        )

    grant = (
        db.query(AgentCapability)
        .filter(AgentCapability.agent_id == agent_id, AgentCapability.capability_id == cap_id)
        .first()
    )
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capability grant not found")

    cap = db.query(Capability).filter(Capability.id == cap_id).first()

    db.delete(grant)
    db.commit()

    log_audit_event(
        db,
        action="capability.revoked",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent_id,
        details={"capability": cap.name if cap else cap_id, "capability_id": cap_id},
        ip_address=request.client.host if request.client else None,
    )
