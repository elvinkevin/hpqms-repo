from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.models import StaffRole, QueueEntryStatus, QueueEntry, Visit
from app.domain.schemas.schemas import QueueEntryRead
from app.domain.services.auth_service import (
    get_current_user,
    require_role,
)
from app.domain.services.queue_service import QueueService

router = APIRouter(
    prefix="/queue",
    tags=["Department Queue Management"],
)

@router.get(
    "/department/{department_id}",
    response_model=list[QueueEntryRead],
    dependencies=[Depends(get_current_user)]
)
async def get_department_queue(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the active queue for a department ordered
    by priority then arrival sequence.
    """

    service = QueueService(db)

    return await service.get_department_queue(
        department_id
    )

@router.get(
    "/entry/{queue_entry_id}",
    response_model=QueueEntryRead,
    dependencies=[Depends(get_current_user)]
)
async def get_queue_entry(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    return await service.get_queue_entry(
        queue_entry_id
    )


@router.get(
    "/visit/{visit_id}",
    response_model=QueueEntryRead | None,
    dependencies=[Depends(get_current_user)]
)
async def get_visit_queue(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    return await service.get_active_queue_entry(
        visit_id
    )


@router.patch(
    "/{queue_entry_id}/call",
    response_model=QueueEntryRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.NURSE,
                StaffRole.DOCTOR,
            )
        )
    ]
)
async def call_patient(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    entry = await service.transition_entry_status(
        queue_entry_id,
        QueueEntryStatus.CALLED,
    )

    await db.commit()

    return entry


@router.patch(
    "/{queue_entry_id}/start",
    response_model=QueueEntryRead,
    dependencies=[Depends(get_current_user)]
)
async def start_service(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    entry = await service.transition_entry_status(
        queue_entry_id,
        QueueEntryStatus.IN_PROGRESS,
    )

    await db.commit()

    return entry

@router.patch(
    "/{queue_entry_id}/complete",
    response_model=QueueEntryRead,
    dependencies=[Depends(get_current_user)]
)
async def complete_queue_step(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    entry = await service.complete_queue_entry(
        queue_entry_id
    )

    await db.commit()

    return entry

@router.patch(
    "/{queue_entry_id}/cancel",
    response_model=QueueEntryRead,
    dependencies=[Depends(get_current_user)]
)
async def cancel_queue_step(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    entry = await service.cancel_queue_entry(
        queue_entry_id
    )

    await db.commit()

    return entry


@router.patch(
    "/{queue_entry_id}/no-show",
    response_model=QueueEntryRead,
    dependencies=[Depends(get_current_user)]
)
async def mark_no_show(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    entry = await service.transition_entry_status(
        queue_entry_id,
        QueueEntryStatus.NO_SHOW,
    )

    await db.commit()

    return entry

@router.get(
    "/{queue_entry_id}/position",
    response_model=int,
    dependencies=[Depends(get_current_user)]
)
async def get_position(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    return await service.get_patient_position(
        queue_entry_id
    )

@router.get(
    "/{queue_entry_id}/wait-time",
    response_model=int,
    dependencies=[Depends(get_current_user)]
)
async def get_wait_time(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = QueueService(db)

    return await service.get_estimated_wait_time(
        queue_entry_id
    )


@router.get(
    "/department/{department_id}/next",
    response_model=QueueEntryRead | None,
    dependencies=[Depends(get_current_user)],
)
async def get_next_patient(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the next patient waiting in a department
    according to priority and arrival order.

    Returns null if the queue is empty.
    """

    service = QueueService(db)

    return await service.get_next_patient(
        department_id
    )