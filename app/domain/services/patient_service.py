from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError  # <-- Import this
from fastapi import HTTPException, status

from app.domain.models.models import Patient
from app.domain.schemas.schemas import PatientCreate


class PatientService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: PatientCreate) -> Patient:
        """
        Create a new patient record.
        Rejects duplicate national_id with a clear error message.
        """
        # 1. Optimistic application-level check (catches 99% of standard duplicates)
        existing = await self.get_by_national_id(data.national_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Patient with national ID '{data.national_id}' already exists. "
                       f"Use GET /patients/{data.national_id} to retrieve the record.",
            )

        try:
            patient = Patient(**data.model_dump())
            self.db.add(patient)
            # Push changes to PostgreSQL to trigger unique constraint checks
            await self.db.flush()
            return patient
            
        except IntegrityError as e:
            # 2. Hard database check (catches simultaneous concurrent inserts)
            # We must use a nested rollback here if we want the session to remain usable,
            # but since FastAPI handles the global rollback on HTTP exception, raising is safe.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflict: A patient with national ID '{data.national_id}' was just registered by another process.",
            )

    async def get_by_national_id(self, national_id: str) -> Patient | None:
        result = await self.db.execute(
            select(Patient).where(Patient.national_id == national_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, patient_id: UUID) -> Patient:
        patient = await self.db.get(Patient, patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient {patient_id} not found",
            )
        return patient
