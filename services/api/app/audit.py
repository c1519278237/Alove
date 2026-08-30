import hashlib

from fastapi import Request
from sqlalchemy.orm import Session

from .models import DataAccessAuditLog


def _ip_hash(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return hashlib.sha256(request.client.host.encode("utf-8")).hexdigest()


def append_audit_log(
    db: Session,
    *,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    reason: str,
    result: str = "allowed",
    request: Request | None = None,
) -> None:
    db.add(
        DataAccessAuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason,
            result=result,
            ip_hash=_ip_hash(request),
        )
    )
