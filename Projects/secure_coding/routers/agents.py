from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from auth.audit_helper import log_audit_event
from auth.dependencies import require_capability
from database import get_db
from models.agent import Agent
from models.api_key import ApiKey
from schemas.agent import AgentCreate, AgentResponse, AgentUpdate, RevokeRequest, SuspendRequest

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("agents:write")),
):
    existing = db.query(Agent).filter(Agent.name == body.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent name already exists")

    agent = Agent(
        name=body.name,
        description=body.description,
        owner=body.owner,
        agent_type=body.agent_type,
        metadata_json=body.metadata_json,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    log_audit_event(
        db,
        action="agent.created",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent.id,
        details={"name": agent.name, "owner": agent.owner},
        ip_address=request.client.host if request.client else None,
    )

    return agent


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("agents:read")),
    status_filter: Optional[str] = Query(None, alias="status"),
    owner: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
):
    query = db.query(Agent)
    if status_filter:
        query = query.filter(Agent.status == status_filter)
    if owner:
        query = query.filter(Agent.owner == owner)
    if agent_type:
        query = query.filter(Agent.agent_type == agent_type)
    return query.all()


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("agents:read")),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("agents:write")),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(agent, field, value)
    agent.updated_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    db.refresh(agent)

    log_audit_event(
        db,
        action="agent.updated",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent.id,
        details={"updated_fields": list(updates.keys())},
        ip_address=request.client.host if request.client else None,
    )

    return agent


@router.post("/{agent_id}/suspend", response_model=AgentResponse)
async def suspend_agent(
    agent_id: str,
    body: SuspendRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("admin:*")),
):
    if agent_id == current_agent["agent_id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot suspend yourself")

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    if agent.status == "revoked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot suspend a revoked agent")

    now = datetime.now(timezone.utc).isoformat()
    agent.status = "suspended"
    agent.suspended_at = now
    agent.updated_at = now
    db.commit()
    db.refresh(agent)

    log_audit_event(
        db,
        action="agent.suspended",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent.id,
        details={"reason": body.reason},
        ip_address=request.client.host if request.client else None,
    )

    return agent


@router.post("/{agent_id}/reactivate", response_model=AgentResponse)
async def reactivate_agent(
    agent_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("admin:*")),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    if agent.status != "suspended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only suspended agents can be reactivated"
        )

    now = datetime.now(timezone.utc).isoformat()
    agent.status = "active"
    agent.suspended_at = None
    agent.updated_at = now
    db.commit()
    db.refresh(agent)

    log_audit_event(
        db,
        action="agent.reactivated",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent.id,
        ip_address=request.client.host if request.client else None,
    )

    return agent


@router.post("/{agent_id}/revoke", response_model=AgentResponse)
async def revoke_agent(
    agent_id: str,
    body: RevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("admin:*")),
):
    if agent_id == current_agent["agent_id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot revoke yourself")

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    if agent.status == "revoked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent already revoked")

    now = datetime.now(timezone.utc).isoformat()
    agent.status = "revoked"
    agent.revoked_at = now
    agent.updated_at = now

    # Cascade: revoke all API keys
    db.query(ApiKey).filter(ApiKey.agent_id == agent_id, ApiKey.status == "active").update(
        {"status": "revoked", "revoked_at": now}
    )

    db.commit()
    db.refresh(agent)

    log_audit_event(
        db,
        action="agent.revoked",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent.id,
        details={"reason": body.reason},
        ip_address=request.client.host if request.client else None,
    )

    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("admin:*")),
):
    if agent_id == current_agent["agent_id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    log_audit_event(
        db,
        action="agent.deleted",
        agent_id=current_agent["agent_id"],
        resource_type="agent",
        resource_id=agent.id,
        details={"name": agent.name},
        ip_address=request.client.host if request.client else None,
    )

    db.delete(agent)
    db.commit()
