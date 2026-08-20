from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import Patient, Visit, QueueEntry
from app.domain.schemas.schemas import (
    KioskCheckInRequest,
    VisitCreate,
)
from app.domain.services.patient_service import PatientService
from app.domain.services.visit_service import VisitService
from app.domain.services.routing_service import RoutingService


class KioskService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.patient_service = PatientService(db)
        self.visit_service = VisitService(db)
        self.routing_service = RoutingService(db)

    async def check_in(
        self,
        data: KioskCheckInRequest,
    ) -> tuple[Patient, Visit, QueueEntry]:
        """Orchestrates the entire atomic kiosk registration and initial routing pipeline."""
        identifier = data.identifier.strip()

        # NOTE: Shifting this check to Pydantic field validation is highly recommended
        if not identifier:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Patient identifier cannot be empty.",
            )

        # 1. Register or fetch the kiosk patient record
        patient = await self.patient_service.register_kiosk_patient(
            identifier=identifier,  # Uses the cleaned up stripped identifier variable
            identifier_type=data.identifier_type,
        )

        # 2. Begin the tracking visit log
        visit = await self.visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=data.visit_type,
                visit_reason="Kiosk check-in",
            )
        )

        # 3. Queue routing logic dispatch
        queue_entry = await self.routing_service.dispatch_initial_kiosk_route(
            visit_id=visit.visit_id
        )

        return patient, visit, queue_entry
