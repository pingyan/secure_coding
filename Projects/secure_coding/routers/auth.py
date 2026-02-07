from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session

from auth.audit_helper import log_audit_event
from auth.hashing import hash_api_key
from auth.jwt import create_access_token
from config import settings
from database import get_db
from models.api_key import ApiKey
from models.capability import AgentCapability, Capability
from schemas.auth import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def exchange_api_key_for_token(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """Exchange an API key for a short-lived JWT."""
    ip = request.client.host if request.client else None

    key_hash = hash_api_key(x_api_key)
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()

    if not api_key:
        log_audit_event(
            db, action="auth.failed", details={"reason": "invalid_key"}, ip_address=ip, success=False
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # Check key status - allow active keys and rotated keys still within grace period
    if api_key.status == "revoked":
        log_audit_event(
            db,
            action="auth.failed",
            agent_id=api_key.agent_id,
            details={"reason": "key_revoked"},
            ip_address=ip,
            success=False,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key has been revoked")

    if api_key.status == "rotated":
        # Check grace period
        if api_key.rotated_at:
            rotated_time = datetime.fromisoformat(api_key.rotated_at)
            now = datetime.now(timezone.utc)
            grace_hours = settings.KEY_ROTATION_GRACE_HOURS
            if (now - rotated_time).total_seconds() > grace_hours * 3600:
                log_audit_event(
                    db,
                    action="auth.failed",
                    agent_id=api_key.agent_id,
                    details={"reason": "rotated_key_expired"},
                    ip_address=ip,
                    success=False,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Rotated API key has expired past grace period",
                )

    # Check key expiration
    if api_key.expires_at:
        expires = datetime.fromisoformat(api_key.expires_at)
        if datetime.now(timezone.utc) > expires:
            log_audit_event(
                db,
                action="auth.failed",
                agent_id=api_key.agent_id,
                details={"reason": "key_expired"},
                ip_address=ip,
                success=False,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key has expired")

    # Check agent status
    agent = api_key.agent
    if agent.status == "suspended":
        log_audit_event(
            db,
            action="auth.failed",
            agent_id=agent.id,
            details={"reason": "agent_suspended"},
            ip_address=ip,
            success=False,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent is suspended")

    if agent.status == "revoked":
        log_audit_event(
            db,
            action="auth.failed",
            agent_id=agent.id,
            details={"reason": "agent_revoked"},
            ip_address=ip,
            success=False,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent has been revoked")

    # Gather capabilities
    caps = (
        db.query(Capability.name)
        .join(AgentCapability, AgentCapability.capability_id == Capability.id)
        .filter(AgentCapability.agent_id == agent.id)
        .all()
    )
    scopes = [c.name for c in caps]

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc).isoformat()
    db.commit()

    token = create_access_token(agent.id, scopes)

    log_audit_event(
        db,
        action="auth.token_issued",
        agent_id=agent.id,
        resource_type="api_key",
        resource_id=api_key.id,
        ip_address=ip,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
    )
