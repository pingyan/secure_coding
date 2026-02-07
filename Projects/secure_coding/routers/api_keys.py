from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth.audit_helper import log_audit_event
from auth.dependencies import require_capability
from auth.hashing import generate_api_key, get_key_prefix, hash_api_key
from config import settings
from database import get_db
from models.agent import Agent
from models.api_key import ApiKey
from schemas.api_key import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse, KeyRotationResponse

router = APIRouter(prefix="/agents/{agent_id}/keys", tags=["api_keys"])


def _get_agent_or_404(db: Session, agent_id: str) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    agent_id: str,
    body: ApiKeyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("keys:manage")),
):
    _get_agent_or_404(db, agent_id)

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    prefix = get_key_prefix(raw_key)

    api_key = ApiKey(
        agent_id=agent_id,
        key_prefix=prefix,
        key_hash=key_hash,
        name=body.name,
        expires_at=body.expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    log_audit_event(
        db,
        action="key.created",
        agent_id=current_agent["agent_id"],
        resource_type="api_key",
        resource_id=api_key.id,
        details={"target_agent": agent_id, "key_name": body.name},
        ip_address=request.client.host if request.client else None,
    )

    return ApiKeyCreatedResponse(
        id=api_key.id,
        agent_id=api_key.agent_id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        raw_key=raw_key,
        status=api_key.status,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    agent_id: str,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("keys:manage")),
):
    _get_agent_or_404(db, agent_id)
    return db.query(ApiKey).filter(ApiKey.agent_id == agent_id).all()


@router.post("/{key_id}/rotate", response_model=KeyRotationResponse)
async def rotate_api_key(
    agent_id: str,
    key_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("keys:manage")),
):
    _get_agent_or_404(db, agent_id)

    old_key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.agent_id == agent_id).first()
    if not old_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if old_key.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active keys can be rotated")

    now = datetime.now(timezone.utc).isoformat()

    # Mark old key as rotated (still valid during grace period)
    old_key.status = "rotated"
    old_key.rotated_at = now

    # Create new key
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    prefix = get_key_prefix(raw_key)

    new_key = ApiKey(
        agent_id=agent_id,
        key_prefix=prefix,
        key_hash=key_hash,
        name=old_key.name,
        expires_at=old_key.expires_at,
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    log_audit_event(
        db,
        action="key.rotated",
        agent_id=current_agent["agent_id"],
        resource_type="api_key",
        resource_id=old_key.id,
        details={"old_key_id": old_key.id, "new_key_id": new_key.id},
        ip_address=request.client.host if request.client else None,
    )

    return KeyRotationResponse(
        old_key_id=old_key.id,
        new_key=ApiKeyCreatedResponse(
            id=new_key.id,
            agent_id=new_key.agent_id,
            key_prefix=new_key.key_prefix,
            name=new_key.name,
            raw_key=raw_key,
            status=new_key.status,
            expires_at=new_key.expires_at,
            created_at=new_key.created_at,
        ),
        grace_period_hours=settings.KEY_ROTATION_GRACE_HOURS,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    agent_id: str,
    key_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("keys:manage")),
):
    _get_agent_or_404(db, agent_id)

    api_key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.agent_id == agent_id).first()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if api_key.status == "revoked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Key already revoked")

    now = datetime.now(timezone.utc).isoformat()
    api_key.status = "revoked"
    api_key.revoked_at = now
    db.commit()

    log_audit_event(
        db,
        action="key.revoked",
        agent_id=current_agent["agent_id"],
        resource_type="api_key",
        resource_id=api_key.id,
        details={"target_agent": agent_id},
        ip_address=request.client.host if request.client else None,
    )
