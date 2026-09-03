from uuid import UUID

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

from app.domain.models.models import StaffRole
from app.domain.schemas.schemas import (
    QueueEntryRead,
    TransferPatientRequest,
    LiveLocationRead,
    CurrentUser,
    VisitRead,
)

from app.domain.services.routing_service import RoutingService
from app.domain.services.auth_service import (
    get_current_user,
    require_role,
    validate_kiosk_api_key,
)


router = APIRouter(
    prefix="/routing",
    tags=["Patient Routing"],
)

# ------------------------------------------------------------------
# INITIAL KIOSK DISPATCH
# ------------------------------------------------------------------

@router.post(
    "/dispatch/{visit_id}",
    response_model=QueueEntryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_kiosk_api_key)],
)
async def dispatch_patient_from_kiosk(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Called immediately after a Visit is created.

    RoutingService determines whether the patient should begin
    at Reception, Triage or Emergency based on the visit and
    patient information.

    The frontend does NOT provide department IDs. Only managed kiosk
    devices with a valid X-Kiosk-API-Key may dispatch a visit.
    
    Required Header:
        X-Kiosk-API-Key: <valid-api-key>
    """
    routing_service = RoutingService(db)

    queue_entry = await routing_service.dispatch_initial_kiosk_route(
        visit_id=visit_id
    )

    await db.commit()
    return queue_entry


# ------------------------------------------------------------------
# TRANSFER BETWEEN DEPARTMENTS
# ------------------------------------------------------------------

@router.post(
    "/{visit_id}/transfer",
    response_model=QueueEntryRead,
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(
            require_role(
                StaffRole.TRIAGE_NURSE,
                StaffRole.DOCTOR,
                StaffRole.ADMIN,  
            )
        )
    ],
)
async def transfer_patient(
    visit_id: UUID,
    payload: TransferPatientRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Transfers an in-progress patient to another department queue.

    This automatically:

    • closes the previous queue entry
    • creates the next queue entry
    • updates Visit.current_queue_entry_id
    • preserves the patient's token number
    
    Required Role: RECEPTIONIST, NURSE, TRIAGE_NURSE, DOCTOR, or ADMIN
    
    Payload:
        {
            "target_dept_id": "uuid",
            "reason": "DEPARTMENT_TRANSFER" | "RETURN_TO_DEPARTMENT" | "DIRECT_ROUTING",
            "priority": "NORMAL" | "URGENT" | "CRITICAL",
            "notes": "optional clinical notes"
        }
    """

    routing_service = RoutingService(db)

    queue_entry = await routing_service.transfer_patient(
        visit_id=visit_id,
        target_dept_id=payload.target_dept_id,
        reason=payload.reason,
        priority=payload.priority,
        notes=payload.notes,
        initiated_by_staff_id=current_user.staff_id,
    )

    await db.commit()
    return queue_entry

# ------------------------------------------------------------------
# DEPRECATED: /move/ endpoint (kept for backward compatibility)
# ------------------------------------------------------------------

@router.post(
    "/move/{visit_id}",
    response_model=QueueEntryRead,
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.NURSE,
                StaffRole.TRIAGE_NURSE,
                StaffRole.DOCTOR,
                StaffRole.ADMIN,
            )
        )
    ],
    deprecated=True,
)
async def move_patient_deprecated(
    visit_id: UUID,
    payload: TransferPatientRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ⚠️  DEPRECATED: Use POST /{visit_id}/transfer instead.
    
    Transfers an in-progress patient to another department queue.
    This is an alias for the /transfer endpoint for backward compatibility.
    """

    routing_service = RoutingService(db)

    queue_entry = await routing_service.transfer_patient(
        visit_id=visit_id,
        target_dept_id=payload.target_dept_id,
        reason=payload.reason,
        priority=payload.priority,
        notes=payload.notes,
        initiated_by_staff_id=current_user.staff_id,
    )

    await db.commit()
    return queue_entry


# ------------------------------------------------------------------
# CURRENT LOCATION
# ------------------------------------------------------------------

@router.get(
    "/location/{visit_id}",
    response_model=LiveLocationRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.NURSE,
                StaffRole.TRIAGE_NURSE,
                StaffRole.DOCTOR,
                StaffRole.ADMIN
            )
        )
    ],
)
async def get_current_location(
    visit_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the patient's current location in the queue system.
    
    Returns the active queue entry, department info, and position in line.
    
    Required Role: Any authenticated staff member
    """
    routing_service = RoutingService(db)
    
    location = await routing_service.get_current_location(visit_id)
    
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visit not found."
        )
    
    return location


# ------------------------------------------------------------------
# MOVEMENT HISTORY
# ------------------------------------------------------------------

@router.get(
    "/history/{visit_id}",
    response_model=list[QueueEntryRead],
    dependencies=[
        Depends(
            require_role(
                StaffRole.ADMIN,
                StaffRole.RECEPTIONIST,
            )
        )
    ],
)
async def get_patient_history(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the complete routing history of a patient's visit.
    
    Shows all departments the patient has visited and their status
    at each stage.
    
    Required Role: ADMIN or RECEPTIONIST
    """

    routing_service = RoutingService(db)

    return await routing_service.get_token_movement_history(
        visit_id
    )


# ------------------------------------------------------------------
# DISCHARGE
# ------------------------------------------------------------------

@router.post(
    "/{visit_id}/discharge",
    response_model=VisitRead,
    status_code=status.HTTP_200_OK,
    dependencies=[
        Depends(
            require_role(
                StaffRole.DOCTOR,
                StaffRole.ADMIN,
            )
        )
    ],
)
async def discharge_patient(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Discharge a patient and complete their visit.
    
    Completes the current queue entry and marks the visit as COMPLETED.
    
    Required Role: DOCTOR or ADMIN
    """
    service = RoutingService(db)

    visit = await service.discharge_patient(
        visit_id=visit_id,
        staff_id=current_user.staff_id,
    )

    await db.commit()

    return visit