from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.services.auth_service import validate_kiosk_api_key
from app.domain.services.kiosk_service import KioskService
from app.domain.schemas.schemas import (
    KioskCheckInRequest,
    KioskCheckInResponse,
)

router = APIRouter(
    prefix="/kiosk",
    tags=["Kiosk"],
)


@router.post(
    "/check-in",
    response_model=KioskCheckInResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_kiosk_api_key)],
)
async def kiosk_check_in(
    data: KioskCheckInRequest,
    db: AsyncSession = Depends(get_db),
):
    async with db.begin():
        service = KioskService(db)

        patient, visit, queue_entry = await service.check_in(data)

    return KioskCheckInResponse(
    patient_id=patient.patient_id,
    visit_id=visit.visit_id,
    queue_entry_id=queue_entry.queue_entry_id,
    token_number=visit.token_number,
    entry_type=visit.entry_type,
    department_id=queue_entry.department_id,
    department_name=queue_entry.department.name,
    status=queue_entry.status,
)
