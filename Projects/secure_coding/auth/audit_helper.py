import json

from sqlalchemy.orm import Session

from models.audit_log import AuditLog


def log_audit_event(
    db: Session,
    *,
    action: str,
    agent_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    success: bool = True,
) -> AuditLog:
    """Create an audit log entry."""
    entry = AuditLog(
        agent_id=agent_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details_json=json.dumps(details) if details else "{}",
        ip_address=ip_address,
        success=1 if success else 0,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
