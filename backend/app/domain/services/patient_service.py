import random
import string
from datetime import date, datetime, timezone
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import Patient, RegistrationStatus, Visit, VisitStage
from app.domain.schemas.schemas import (
    CompletePatientRegistration,
    PatientCreate,
    EmergencyPatientCreate,
    PatientIdentifierType,
    PatientReconciliation,
    PatientUpdate,
)


class PatientService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    async def _generate_temporary_identifier(self) -> str:
        """
        Generate a unique, human-readable temporary badge for Emergency Intake.
        Format: TEMP-YYYYMMDD-XXXX (e.g., TEMP-20260728-9812)
        """
        date_str = date.today().strftime("%Y%m%d")

        while True:
            suffix = "".join(random.choices(string.digits, k=4))
            temp_id = f"TEMP-{date_str}-{suffix}"

            existing = await self.get_by_temporary_identifier(temp_id)
            if not existing:
                return temp_id

    async def _validate_unique_identity(
        self,
        national_id: str | None = None,
        phone: str | None = None,
        exclude_patient_id: UUID | None = None,
    ) -> None:
        """
        Validate that National ID or Phone does not conflict with existing records.
        """
        if national_id:
            existing = await self.get_by_national_id(national_id)
            if existing and existing.patient_id != exclude_patient_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Patient with National ID '{national_id}' already exists.",
                )

        if phone:
            existing = await self.get_by_phone(phone)
            if existing and existing.patient_id != exclude_patient_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Patient with Phone number '{phone}' already exists.",
                )

    # ------------------------------------------------------------------
    # LOOKUPS & MAINTENANCE
    # ------------------------------------------------------------------

    async def get_by_id(self, patient_id: UUID) -> Patient:
        result = await self.db.execute(
            select(Patient).where(Patient.patient_id == patient_id)
        )
        patient = result.scalar_one_or_none()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with ID '{patient_id}' not found.",
            )
        return patient

    async def get_by_national_id(self, national_id: str) -> Patient | None:
        result = await self.db.execute(
            select(Patient).where(Patient.national_id == national_id)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Patient | None:
        result = await self.db.execute(
            select(Patient).where(Patient.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_by_temporary_identifier(self, temp_id: str) -> Patient | None:
        result = await self.db.execute(
            select(Patient).where(Patient.temporary_identifier == temp_id)
        )
        return result.scalar_one_or_none()

    async def find_patient(self, query: str) -> Patient:
        """
        Find a single patient by National ID, Phone, or Temporary Identifier.
        """
        result = await self.db.execute(
            select(Patient).where(
                or_(
                    Patient.national_id == query,
                    Patient.phone == query,
                    Patient.temporary_identifier == query,
                )
            )
        )
        patient = result.scalar_one_or_none()
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No patient found matching search query '{query}'.",
            )
        return patient

    async def search_patients(self, query: str) -> Sequence[Patient]:
        """
        Search patients matching name, national ID, phone, or temporary badge.
        """
        stmt = select(Patient).where(
            or_(
                Patient.first_name.ilike(f"%{query}%"),
                Patient.last_name.ilike(f"%{query}%"),
                Patient.national_id.ilike(f"%{query}%"),
                Patient.phone.ilike(f"%{query}%"),
                Patient.temporary_identifier.ilike(f"%{query}%"),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # ------------------------------------------------------------------
    # DOMAIN WORKFLOW METHODS
    # ------------------------------------------------------------------

    async def register_standard_patient(self, data: PatientCreate) -> Patient:
        """
        Standard demographic registration for planned or non-emergency visits.
        """
        # Centralized Identity Check
        await self._validate_unique_identity(
            national_id=data.national_id,
            phone=data.phone,
        )

        patient = Patient(
            **data.model_dump(),
            registration_status=RegistrationStatus.COMPLETE,
        )

        try:
            self.db.add(patient)
            await self.db.flush()
            await self.db.refresh(patient)
            return patient
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not register patient due to a database integrity constraint.",
            )

    async def register_emergency_patient(
        self, data: EmergencyPatientCreate
    ) -> Patient:
        """
        Rapid John Doe / Emergency intake.
        Validates identity if provided, otherwise generates temporary badge.
        """
        # Validate identity if conscious patient provides partial ID/Phone
        await self._validate_unique_identity(
            national_id=getattr(data, "national_id", None),
            phone=getattr(data, "phone", None),
        )

        temp_id = await self._generate_temporary_identifier()

        patient = Patient(
            **data.model_dump(),
            temporary_identifier=temp_id,
            registration_status=RegistrationStatus.INCOMPLETE,
        )

        try:
            self.db.add(patient)
            await self.db.flush()
            await self.db.refresh(patient)
            return patient
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not generate unique temporary emergency intake.",
            )

    async def reconcile_patient(
        self,
        patient_id: UUID,
        reconcile_data: PatientReconciliation,
        staff_id: UUID,
    ) -> Patient:
        """
        Retrospectively update a temporary emergency record with verified official
        demographics and transition status to COMPLETE.
        """
        patient = await self.get_by_id(patient_id)

        # Business Rule: Prevent double reconciliation
        if patient.registration_status == RegistrationStatus.COMPLETE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Patient record is already COMPLETE and has been reconciled.",
            )

        # Validate duplicate National ID or Phone before upgrading status
        await self._validate_unique_identity(
            national_id=reconcile_data.national_id,
            phone=reconcile_data.phone,
            exclude_patient_id=patient_id,
        )

        updates = reconcile_data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(patient, field, value)

        patient.registration_status = RegistrationStatus.COMPLETE
        patient.reconciled_at = datetime.now(timezone.utc)
        patient.reconciled_by = staff_id

        try:
            await self.db.flush()
            await self.db.refresh(patient)
            return patient
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflict encountered while reconciling patient demographic identity.",
            )

    async def update_patient(
        self, patient_id: UUID, data: PatientUpdate
    ) -> Patient:
        """
        Update demographic info for an existing patient.
        """
        patient = await self.get_by_id(patient_id)

        # Reuse centralized validation
        await self._validate_unique_identity(
            national_id=data.national_id,
            phone=data.phone,
            exclude_patient_id=patient_id,
        )

        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(patient, field, value)

        try:
            await self.db.flush()
            await self.db.refresh(patient)
            return patient
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not update patient due to a database constraint.",
            )


    async def register_kiosk_patient(
        self,
        identifier: str,
        identifier_type: PatientIdentifierType,
    ) -> Patient:
        """Find or create the minimal patient record required for kiosk check-in."""

        identifier = identifier.strip()

        if not identifier:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Patient identifier cannot be empty.",
            )

        # ---------------------------------------------------------
        # 1. Validate according to the declared identifier type
        # ---------------------------------------------------------

        if identifier_type == PatientIdentifierType.PHONE:
            if not identifier.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Phone number must contain digits only.",
                )

            if len(identifier) != 10:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Phone number must contain 10 digits.",
                )

        elif identifier_type == PatientIdentifierType.NATIONAL_ID:
            if not identifier.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="National ID must contain digits only.",
                )

        # ---------------------------------------------------------
        # 2. Look for an existing patient
        # ---------------------------------------------------------

        existing = await self.find_patient_optional(identifier)

        if existing:
            return existing

        # ---------------------------------------------------------
        # 3. Create minimal incomplete patient
        # ---------------------------------------------------------

        patient_kwargs = {
            "registration_status": RegistrationStatus.INCOMPLETE,
        }

        if identifier_type == PatientIdentifierType.PHONE:
            patient_kwargs["phone"] = identifier
        else:
            patient_kwargs["national_id"] = identifier

        patient = Patient(**patient_kwargs)

        # ---------------------------------------------------------
        # 4. Protect against concurrent registration
        # ---------------------------------------------------------

        try:
            self.db.add(patient)
            await self.db.flush()
            await self.db.refresh(patient)

            return patient

        except IntegrityError:
            await self.db.rollback()

            existing = await self.find_patient_optional(identifier)

            if existing:
                return existing

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Conflict detected. A patient record with this "
                    "identifier is already being processed."
                ),
            )

    async def find_patient_optional(
        self,
        query: str,
    ) -> Patient | None:
        result = await self.db.execute(
            select(Patient).where(
                or_(
                    Patient.national_id == query,
                    Patient.phone == query,
                    Patient.temporary_identifier == query,
                )
            )
        )

        return result.scalar_one_or_none()


    async def complete_patient_registration(
        self,
        patient_id: UUID,
        data: CompletePatientRegistration,
    ) -> Patient:
        """
        Completes the registration of an existing incomplete patient.
        """

        patient = await self.get_by_id(patient_id)

        # A temporary emergency patient should use the
        # dedicated reconciliation workflow.
        if patient.temporary_identifier is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Temporary emergency patients must be "
                    "reconciled using the reconciliation workflow."
                ),
            )

        # Validate national ID / phone uniqueness against
        # other patient records.
        await self._validate_unique_identity(
            national_id=data.national_id,
            phone=data.phone,
            exclude_patient_id=patient_id,
        )

        updates = data.model_dump(exclude_unset=True)

        for field, value in updates.items():
            setattr(patient, field, value)

        patient.registration_status = RegistrationStatus.COMPLETE

        try:
            await self.db.flush()
            await self.db.refresh(patient)

            return patient

        except IntegrityError:
            await self.db.rollback()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Could not complete patient registration "
                    "due to a database constraint."
                ),
            )
        
    async def set_active_status(
        self,
        patient_id: UUID,
        is_active: bool,
    ) -> Patient:
        """
        Activates or deactivates a patient record.

        A patient cannot be deactivated while they have
        an active hospital visit.
        """

        patient = await self.get_by_id(patient_id)

        # Nothing to do if the requested state is already current.
        if patient.is_active == is_active:
            return patient

        # Only check for an active visit when deactivating.
        if not is_active:
            active_visit = await self.db.execute(
                select(Visit).where(
                    Visit.patient_id == patient_id,
                    Visit.stage == VisitStage.ACTIVE,
                )
            )

            if active_visit.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Cannot deactivate patient with an active visit."
                    ),
                )

        patient.is_active = is_active

        await self.db.flush()
        await self.db.refresh(patient)

        return patient