from uuid import UUID
from typing import Optional, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.models import AuditLog


class AuditService:
    """
    Audit Logger Service Engine.
    Ensures an append-only transaction ledger for tracking hospital operations.
    No updates, no deletes.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # APPEND LOG ACTION
    # ------------------------------------------------------------------
    async def log_action(
        self,
        entity_id: UUID,
        entity_type: str,
        action: str,
        performed_by: Optional[UUID] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Appends an immutable audit record to the tracking footprint log.
        No flush executed here - relies entirely on the parent transaction context.
        """
        entry = AuditLog(
            entity_id=entity_id,
            entity_type=entity_type,
            action=action.strip().upper(),
            performed_by=performed_by,
            payload=payload or {},
        )
        self.db.add(entry)

    # ------------------------------------------------------------------
    # READ OPERATIONS: PERFORMANCE AUDIT TIMELINES
    # ------------------------------------------------------------------
    async def get_entity_history(self, entity_id: UUID, entity_type: str) -> List[AuditLog]:
        """
        Dashboard Support Utility: Fetches the chronological audit history for a specific
        target entity (e.g., pulling a full access audit trail for a single Patient or Visit).
        """
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.entity_id == entity_id,
                AuditLog.entity_type == entity_type
            )
            .order_by(AuditLog.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
