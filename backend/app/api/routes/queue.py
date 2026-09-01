from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db.session import get_db
from app.domain.models.models import QueueEntry, QueueEntryStatus, StaffRole, Visit
from app.domain.schemas.schemas import CurrentUser, QueueEntryRead
from app.domain.services.auth_service import (
    ensure_department_access,
    get_current_user,
    require_role,
)
from app.domain.services.queue_service import QueueService

router = APIRouter(
    prefix="/queue",
    tags=["Department Queue Management"],
)


# ==========================================
# QUEUE READ ENDPOINTS
# ==========================================

@router.get(
    "/department/{dept_id}",
    response_model=list[QueueEntryRead],
)
async def get_department_queue(
    dept_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the active queue for the staff member's department."""
    ensure_department_access(current_user, dept_id)

    service = QueueService(db)
    return await service.get_department_queue(dept_id)


@router.get(
    "/department/{dept_id}/next",
    response_model=QueueEntryRead | None,
)
async def get_next_patient(
    dept_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the next patient waiting in a department according to priority and arrival order."""
    ensure_department_access(current_user, dept_id)

    service = QueueService(db)
    return await service.get_next_patient(dept_id)


@router.get(
    "/entry/{queue_entry_id}",
    response_model=QueueEntryRead,
)
async def get_queue_entry(
    queue_entry_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    entry = await service.get_queue_entry(queue_entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue entry not found.",
        )

    ensure_department_access(current_user, entry.dept_id)
    return entry


@router.get(
    "/visit/{visit_id}",
    response_model=QueueEntryRead | None,
)
async def get_visit_queue(
    visit_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    entry = await service.get_active_queue_entry(visit_id)
    
    if entry:
        ensure_department_access(current_user, entry.dept_id)
        
    return entry


# ==========================================
# QUEUE MUTATION ENDPOINTS
# ==========================================

@router.patch(
    "/{queue_entry_id}/call",
    response_model=QueueEntryRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.NURSE,
                StaffRole.DOCTOR,
                StaffRole.TRIAGE_NURSE,
                StaffRole.ADMIN,

            )
        )
    ],
)
async def call_patient(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    service = QueueService(db)

    entry = await service.call_queue_entry(
        queue_entry_id,
        staff_id=current_user.staff_id,
    )

    await db.commit()
    await service.emit_display_event(entry)
    return entry


@router.patch(
    "/{queue_entry_id}/start",
    response_model=QueueEntryRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.NURSE,
                StaffRole.DOCTOR,
            )
        )
    ],
)
async def start_patient(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    service = QueueService(db)

    entry = await service.start_queue_entry(
        queue_entry_id,
        staff_id=current_user.staff_id,
    )

    await db.commit()

    await service.emit_display_event(entry)

    return entry


@router.patch(
    "/{queue_entry_id}/complete",
    response_model=QueueEntryRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.NURSE,
                StaffRole.DOCTOR,
            )
        )
    ],
)
async def complete_queue_entry(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    service = QueueService(db)

    entry = await service.transition_entry_status(
        queue_entry_id,
        QueueEntryStatus.COMPLETED,
        staff_id=current_user.staff_id,  # <-- Ensure staff_id is passed here
    )

    await db.commit()
    await service.emit_display_event(entry)

    return entry

@router.patch(
    "/{queue_entry_id}/cancel",
    response_model=QueueEntryRead,
)
async def cancel_queue_step(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_role(
            StaffRole.RECEPTIONIST,
            StaffRole.NURSE,
            StaffRole.DOCTOR,
        )
    ),
):
    service = QueueService(db)
    entry = await service.get_queue_entry(queue_entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue entry not found.",
        )

    ensure_department_access(current_user, entry.dept_id)

    # Align with complete_queue_entry by passing staff_id to the service layer
    entry = await service.cancel_queue_entry(
        queue_entry_id,
        staff_id=current_user.staff_id,
    )

    await db.commit()
    await service.emit_display_event(entry)
    
    return entry

@router.get(
    "/department/{dept_id}/no-show",
    response_model=List[QueueEntryRead],
)
async def get_department_no_show_queue(
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    service = QueueService(db)

    return await service.get_department_no_show_queue(
        dept_id,
        staff_id=current_user.staff_id,
    )


@router.patch(
    "/{queue_entry_id}/requeue",
    response_model=QueueEntryRead,
)
async def requeue_queue_entry(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    service = QueueService(db)

    # --------------------------------------------------------------
    # 1. Perform state transition
    # --------------------------------------------------------------

    await service.requeue_queue_entry(
        queue_entry_id,
        staff_id=current_user.staff_id,
    )

    # --------------------------------------------------------------
    # 2. Commit transaction
    # --------------------------------------------------------------

    await db.commit()

    # --------------------------------------------------------------
    # 3. Reload committed state with ALL relationships needed by:
    #    - display event
    #    - staff event
    #    - QueueEntryRead response
    # --------------------------------------------------------------

    stmt = (
        select(QueueEntry)
        .options(
            selectinload(QueueEntry.visit).selectinload(Visit.patient),
            selectinload(QueueEntry.department),
        )
        .where(QueueEntry.queue_entry_id == queue_entry_id)
    )

    result = await db.execute(stmt)
    entry = result.scalar_one()

    # --------------------------------------------------------------
    # 4. Publish canonical display event AFTER commit
    # --------------------------------------------------------------

    await service.emit_display_event(
        entry,
        event_type="TOKEN_REQUEUED",
    )

    # --------------------------------------------------------------
    # 5. Publish staff event
    # --------------------------------------------------------------

    await service.emit_department_event(
        entry,
        event_type="TOKEN_REQUEUED",
    )

    # --------------------------------------------------------------
    # 6. Return fully-loaded object
    # --------------------------------------------------------------

    return entry


# ==========================================
# STATISTICAL METRICS (READ-ONLY)
# ==========================================

@router.get(
    "/{queue_entry_id}/position",
    response_model=int,
)
async def get_position(
    queue_entry_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    entry = await service.get_queue_entry(queue_entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue entry not found.",
        )

    ensure_department_access(current_user, entry.dept_id)
    return await service.get_patient_position(queue_entry_id)


@router.get(
    "/{queue_entry_id}/wait-time",
    response_model=int,
)
async def get_wait_time(
    queue_entry_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = QueueService(db)
    entry = await service.get_queue_entry(queue_entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue entry not found.",
        )

    ensure_department_access(current_user, entry.dept_id)
    return await service.get_estimated_wait_time(queue_entry_id)


@router.patch(
        "/{queue_entry_id}/no-show", 
        response_model=QueueEntryRead
        )
async def mark_no_show(
    queue_entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    service = QueueService(db)

    entry = await service.mark_no_show(
        queue_entry_id=queue_entry_id,
        staff_id=current_user.staff_id,
    )

    await db.commit()
    await service.emit_display_event(entry)

    return entry