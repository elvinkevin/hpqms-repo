"""
Audit logger — every meaningful state change calls log_action().
The audit_log table is append-only: no updates, no deletes.
"""
from uuid import UUID
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.models import AuditLog


async def log_action(
    db: AsyncSession,
    entity_id: UUID,
    entity_type: str,
    action: str,
    performed_by: Optional[UUID] = None,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    entry = AuditLog(
        entity_id=entity_id,
        entity_type=entity_type,
        action=action,
        performed_by=performed_by,
        payload=payload or {},
    )
    db.add(entry)
    # No flush here — caller's transaction handles it
