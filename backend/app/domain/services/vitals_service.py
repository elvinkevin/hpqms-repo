from typing import Sequence, Optional
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import Visit, Vitals
from app.domain.schemas.schemas import VitalsCreate, TriageAssessmentUpdate


class VitalsService:
    @staticmethod
    async def record_vitals(
        db: AsyncSession,
        visit_id: UUID,
        staff_id: UUID,
        vitals_in: VitalsCreate,
    ) -> Vitals:
        """Records a new vitals entry for a visit."""
        # 1. Verify visit exists
        result = await db.execute(
            select(Visit).where(Visit.visit_id == visit_id)
        )
        visit = result.scalar_one_or_none()
        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Visit with ID {visit_id} not found.",
            )

        # 2. Create Vitals record
        vitals_data = vitals_in.model_dump(exclude_unset=True)
        vitals = Vitals(
            visit_id=visit_id,
            recorded_by=staff_id,
            **vitals_data,
        )
        db.add(vitals)
        await db.commit()
        await db.refresh(vitals)
        return vitals

    @staticmethod
    async def get_latest_vitals(
        db: AsyncSession,
        visit_id: UUID,
    ) -> Optional[Vitals]:
        """Gets the most recent vitals entry for a visit."""
        stmt = (
            select(Vitals)
            .where(Vitals.visit_id == visit_id)
            .order_by(Vitals.recorded_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_vitals(
        db: AsyncSession,
        visit_id: UUID,
    ) -> Sequence[Vitals]:
        """Gets full vitals history for a visit, ordered newest first."""
        stmt = (
            select(Vitals)
            .where(Vitals.visit_id == visit_id)
            .order_by(Vitals.recorded_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def update_triage_assessment(
        db: AsyncSession,
        visit_id: UUID,
        assessment_in: TriageAssessmentUpdate,
    ) -> Visit:
        """Updates chief complaint / triage assessment / triage priority
        on a visit. Partial update — only provided fields are changed."""
        result = await db.execute(
            select(Visit).where(Visit.visit_id == visit_id)
        )
        visit = result.scalar_one_or_none()
        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Visit with ID {visit_id} not found.",
            )

        if assessment_in.chief_complaint is not None:
            visit.chief_complaint = assessment_in.chief_complaint
        if assessment_in.triage_assessment is not None:
            visit.triage_assessment = assessment_in.triage_assessment
        await db.flush()
        await db.refresh(visit)
        return visit
