from datetime import datetime, timezone
import zoneinfo  # Standard library in Python 3.9+
from typing import List, Optional, Final
from uuid import UUID

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.domain.models.models import (
    Queue, QueueToken, TokenStatus, TriageLevel, Department, Patient
)

# 1. Establish your clinic's actual operational timezone
CLINIC_TZ = zoneinfo.ZoneInfo("Africa/Nairobi")

TRIAGE_ORDER = {
    TriageLevel.CRITICAL: 0,
    TriageLevel.URGENT: 1,
    TriageLevel.SEMI_URGENT: 2,
    TriageLevel.NON_URGENT: 3,
}

# Convert triage order into a database CASE expression builder
TRIAGE_DB_ORDER = case(
    (QueueToken.triage_level == TriageLevel.CRITICAL, TRIAGE_ORDER[TriageLevel.CRITICAL]),
    (QueueToken.triage_level == TriageLevel.URGENT, TRIAGE_ORDER[TriageLevel.URGENT]),
    (QueueToken.triage_level == TriageLevel.SEMI_URGENT, TRIAGE_ORDER[TriageLevel.SEMI_URGENT]),
    (QueueToken.triage_level == TriageLevel.NON_URGENT, TRIAGE_ORDER[TriageLevel.NON_URGENT]),
    else_=99
)

ACTIVE_STATUSES = [
    TokenStatus.ISSUED, TokenStatus.WAITING,
    TokenStatus.IN_TRIAGE, TokenStatus.ESCALATED,
    TokenStatus.CALLED, TokenStatus.IN_CONSULT,
]

VALID_TRANSITIONS: Final = {
    TokenStatus.ISSUED:      frozenset({TokenStatus.WAITING, TokenStatus.CANCELLED}),
    TokenStatus.WAITING:     frozenset({TokenStatus.IN_TRIAGE, TokenStatus.CALLED, TokenStatus.CANCELLED}),
    TokenStatus.IN_TRIAGE:   frozenset({TokenStatus.WAITING, TokenStatus.ESCALATED}),
    TokenStatus.ESCALATED:   frozenset({TokenStatus.CALLED}),
    TokenStatus.CALLED:      frozenset({TokenStatus.IN_CONSULT, TokenStatus.WAITING}),
    TokenStatus.IN_CONSULT:  frozenset({TokenStatus.COMPLETED, TokenStatus.TRANSFERRED}),
    TokenStatus.COMPLETED:   frozenset(),
    TokenStatus.TRANSFERRED: frozenset(),
    TokenStatus.CANCELLED:   frozenset(),
}

AVG_CONSULT_MINUTES = 8


class QueueService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Queue management ──────────────────────────────────────────────────

    async def get_or_create_todays_queue(self, dept_id: UUID) -> Queue:
        """Return today's open queue, utilizing explicit clinic timezone logic."""
        today_local = datetime.now(CLINIC_TZ).date()
        
        result = await self.db.execute(
            select(Queue).where(
                and_(Queue.dept_id == dept_id, Queue.queue_date == today_local)
            )
        )
        queue = result.scalar_one_or_none()

        if not queue:
            queue = Queue(dept_id=dept_id, queue_date=today_local, status="OPEN")
            self.db.add(queue)
            await self.db.flush()

        return queue

    async def get_ordered_tokens(self, queue_id: UUID) -> List[QueueToken]:
        """ 
        1. Filters rows by matching queue_id and checking if status is in ACTIVE_STATUSES.
        2. Optimizes performance via selectinload to eagerly fetch patient relationships (prevents N+1 queries).
        3. Sorts results via PostgreSQL by triage priority tier first, then chronologically (FIFO).
        """
        result = await self.db.execute(
            select(QueueToken)
            .options(selectinload(QueueToken.patient))
            .where(
                and_(
                    QueueToken.queue_id == queue_id,
                    QueueToken.status.in_(ACTIVE_STATUSES),
                )
            )
            .order_by(TRIAGE_DB_ORDER, QueueToken.issued_at.asc())
        )
        return list(result.scalars().all())

    # ── Token issuance ───────────────────────────────────────────────────

    async def issue_token(
        self,
        patient_id: UUID,
        dept_id: UUID,
        notes: Optional[str] = None,
    ) -> QueueToken:
        """Creates a token safely with concurrency protections."""
        patient = await self.db.get(Patient, patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        dept = await self.db.get(Department, dept_id)
        if not dept or not dept.is_active:
            raise HTTPException(status_code=404, detail=f"Department {dept_id} inactive")

        # 1. Atomic Queue Isolation
        queue = await self.get_or_create_todays_queue(dept_id)
        
        # 2. LOCK THE ENTIRE QUEUE ROW FOR THIS DEPARTMENT
        # This completely isolates the sequence calculation blocks across concurrent workers
        await self.db.execute(
            select(Queue)
            .where(Queue.queue_id == queue.queue_id)
            .with_for_update()
        )
        
        # 3. Calculate sequence number safely inside the lock boundary
        token_number = await self._next_token_number_locked(queue.queue_id, dept.code)

        token = QueueToken(
            queue_id=queue.queue_id,
            patient_id=patient_id,
            token_number=token_number,
            status=TokenStatus.WAITING,
            triage_level=TriageLevel.NON_URGENT,
            notes=notes,
        )
        self.db.add(token)
        await self.db.flush()

        result = await self.db.execute(
            select(QueueToken)
            .options(selectinload(QueueToken.patient), selectinload(QueueToken.queue))
            .where(QueueToken.token_id == token.token_id)
        )
        return result.scalar_one()

    async def _next_token_number_locked(self, queue_id: UUID, dept_code: str) -> str:
        """Counts existing records safely using the locked context of the parent row."""
        stmt = (
            select(func.count(QueueToken.token_id))
            .where(QueueToken.queue_id == queue_id)
            # !!! .with_for_update() removed from here to fix PostgreSQL FeatureNotSupportedError !!!
        )
        result = await self.db.execute(stmt)
        count = result.scalar_one()
        return f"{dept_code}-{str(count + 1).zfill(3)}"

    # ── Status transitions ────────────────────────────────────────────────

    async def update_token_status(
        self,
        token_id: UUID,
        new_status: TokenStatus,
        notes: Optional[str] = None,
    ) -> QueueToken:
        token = await self.db.get(QueueToken, token_id, options=[selectinload(QueueToken.patient)])
        if not token:
            raise HTTPException(status_code=404, detail=f"Token {token_id} not found")

        allowed = VALID_TRANSITIONS.get(token.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot transition {token.status} → {new_status}. Allowed: {[s.value for s in allowed]}"
            )

        token.status = new_status
        if notes:
            token.notes = notes

        now = datetime.now(timezone.utc)
        if new_status == TokenStatus.CALLED:
            token.called_at = now
        elif new_status in (TokenStatus.COMPLETED, TokenStatus.TRANSFERRED):
            token.completed_at = now

        await self.db.flush()
        return token

    # ── Wait time estimate ────────────────────────────────────────────────

    async def get_estimated_wait(self, token_id: UUID) -> int:
        """Computes wait times via an atomic database COUNT query."""
        token = await self.db.get(QueueToken, token_id)
        if not token:
            raise HTTPException(status_code=404, detail="Token not found")

        if token.status not in ACTIVE_STATUSES:
            return 0

        # Build conditions to count how many patients are legally ahead of this specific token
        current_priority_val = TRIAGE_ORDER.get(token.triage_level, 99)

        stmt = (
            select(func.count(QueueToken.token_id))
            .where(
                and_(
                    QueueToken.queue_id == token.queue_id,
                    QueueToken.status.in_(ACTIVE_STATUSES),
                    # Count higher triage levels OR same level with an older timestamp (FIFO)
                    (
                        (TRIAGE_DB_ORDER < current_priority_val) |
                        and_(TRIAGE_DB_ORDER == current_priority_val, QueueToken.issued_at < token.issued_at)
                    )
                )
            )
        )
        result = await self.db.execute(stmt)
        position = result.scalar_one()

        return position * AVG_CONSULT_MINUTES
