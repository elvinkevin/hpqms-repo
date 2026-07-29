from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import (
    QueueEntry,
    QueueEntryStatus,
    Visit,
    Patient,
    VisitStage,
)
from app.domain.schemas.schemas import VisitCreate
from app.domain.services.token_service import TokenService


class VisitService:
    """
    Handles the lifecycle of a patient visit.

    Responsibilities
    ----------------
    - Start a visit
    - Generate a visit token
    - Retrieve visits
    - Retrieve active visits
    - Complete visits
    - Cancel visits
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_service = TokenService(db)

    # ==========================================================
    # READ
    # ==========================================================

    async def get_visit(self, visit_id: UUID) -> Visit:
        visit = await self.db.get(Visit, visit_id)

        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Visit not found.",
            )

        return visit

    async def get_active_visit(
        self,
        patient_id: UUID,
    ) -> Visit | None:

        result = await self.db.execute(
            select(Visit).where(
                Visit.patient_id == patient_id,
                Visit.stage == VisitStage.ACTIVE,
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # CREATE
    # ==========================================================

    async def start_visit(
        self,
        data: VisitCreate,
    ) -> Visit:
        """
        Starts a new hospital visit.

        Automatically requests a token from TokenService.
        """

        patient = await self.db.get(
            Patient,
            data.patient_id,
        )

        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )

        existing = await self.get_active_visit(
            patient.patient_id
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Patient already has an active visit.",
            )

        token = await self.token_service.generate_token(
            data.entry_type
        )

        visit = Visit(
            patient_id=data.patient_id,
            token_number=token,
            entry_type=data.entry_type,
            visit_reason=data.visit_reason,
            stage=VisitStage.ACTIVE,
        )

        self.db.add(visit)

        await self.db.flush()
        await self.db.refresh(visit)

        return visit

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def complete_visit(
        self,
        visit_id: UUID,
    ) -> Visit:
        """
        Complete a hospital visit.

        A visit may only be completed when there are no active
        queue entries remaining for the patient.
        """

        active_queue = await self.db.execute(
            select(QueueEntry).where(
                QueueEntry.visit_id == visit_id,
                QueueEntry.status.in_(
                    [
                        QueueEntryStatus.WAITING,
                        QueueEntryStatus.CALLED,
                        QueueEntryStatus.IN_PROGRESS,
                    ]
                ),
            )
        )

        if active_queue.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Patient still has an active queue entry.",
            )

        return await self._close_visit(
            visit_id,
            VisitStage.COMPLETED,
        )

    async def cancel_visit(
        self,
        visit_id: UUID,
    ) -> Visit:

        return await self._close_visit(
            visit_id,
            VisitStage.CANCELLED,
        )

    async def _close_visit(
        self,
        visit_id: UUID,
        stage: VisitStage,
    ) -> Visit:

        visit = await self.get_visit(visit_id)

        visit.stage = stage
        visit.completed_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(visit)

        return visit