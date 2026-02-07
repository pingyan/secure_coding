from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth.dependencies import require_capability
from database import get_db
from models.audit_log import AuditLog
from schemas.audit import AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogResponse])
async def query_audit_logs(
    db: Session = Depends(get_db),
    current_agent: dict = Depends(require_capability("audit:read")),
    agent_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(AuditLog)

    if agent_id:
        query = query.filter(AuditLog.agent_id == agent_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)

    return query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
