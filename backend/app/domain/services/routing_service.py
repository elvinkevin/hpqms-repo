from uuid import UUID
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.models import (
    QueueEntryStatus,
    Visit,
    QueueEntry,
    QueuePriority,
    EntryType,
    RegistrationStatus,
    VisitStage,
)

from app.domain.services.visit_service import VisitService
from app.domain.services.queue_service import QueueService
from app.domain.services.departments_service import DepartmentService
from app.domain.schemas.schemas import TransferReason


class RoutingService:
    """
    Coordinates patient movement throughout the hospital.

    Responsibilities:
        • Initial kiosk dispatch
        • Department-to-department transfers
        • Live location tracking
        • Queue journey history

    This service intentionally delegates all database-specific work
    to the VisitService, QueueService, and DepartmentService.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.visit_service = VisitService(db)
        self.queue_service = QueueService(db)
        self.department_service = DepartmentService(db)

    async def dispatch_initial_kiosk_route(
        self,
        visit_id: UUID,
    ) -> QueueEntry:

        visit = await self.visit_service.get_visit(visit_id)

        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Visit not found.",
            )

        patient = visit.patient

        # ---------------------------------------------------------
        # Emergency patients bypass the normal workflow
        # ---------------------------------------------------------
        if visit.entry_type == EntryType.EMERGENCY:

            emergency = await self.department_service.get_by_code(
                "EMERGENCY"
            )

            return await self.transfer_patient(
                visit_id=visit.visit_id,
                target_department_id=emergency.dept_id,
                reason=TransferReason.DIRECT_ROUTING,
                priority=QueuePriority.CRITICAL,
                notes="Emergency patient routed directly to Emergency.",
            )

        # ---------------------------------------------------------
        # Temporary / Incomplete registrations go to Reception
        # ---------------------------------------------------------
        if patient.registration_status == RegistrationStatus.INCOMPLETE:

            reception = await self.department_service.get_by_code(
                "REC"
            )

            return await self.transfer_patient(
                visit_id=visit.visit_id,
                target_department_id=reception.dept_id,
                reason=TransferReason.DIRECT_ROUTING,
                priority=QueuePriority.NORMAL,
                notes="Patient requires registration.",
            )

        # ---------------------------------------------------------
        # Appointment patients bypass Reception
        # ---------------------------------------------------------
        if visit.entry_type == EntryType.APPOINTMENT:

            triage = await self.department_service.get_by_code(
                "TRIAGE"
            )

            return await self.transfer_patient(
                visit_id=visit.visit_id,
                target_department_id=triage.dept_id,
                reason=TransferReason.DIRECT_ROUTING,
                priority=QueuePriority.NORMAL,
                notes="Appointment patient routed directly to Triage.",
            )

        # ---------------------------------------------------------
        # Walk-ins & Referrals
        # ---------------------------------------------------------
        reception = await self.department_service.get_by_code(
            "REC"
        )

        return await self.transfer_patient(
            visit_id=visit.visit_id,
            target_department_id=reception.dept_id,
            reason=TransferReason.DIRECT_ROUTING,
            priority=QueuePriority.NORMAL,
            notes="Walk-in patient routed to Reception.",
        )
    # ---------------------------------------------------------
    # MOVE PATIENT
    # ---------------------------------------------------------

    async def transfer_patient(
        self,
        visit_id: UUID,
        target_department_id: UUID,
        reason: TransferReason = TransferReason.DEPARTMENT_TRANSFER,
        priority: QueuePriority = QueuePriority.NORMAL,
        notes: Optional[str] = None,
        initiated_by_staff_id: Optional[UUID] = None,
    ) -> QueueEntry:
        """
        Orchestrates an inter-departmental TRANSFER command:
        1. Validates visit state and target department.
        2. Applies priority escalation rules based on TransferReason.
        3. Enforces guardrails (e.g., CRITICAL priority requires notes).
        4. Completes current active QueueEntry (frees doctor/staff slot).
        5. Creates new QueueEntry (WAITING) for target department.
        6. Emits WebSocket 'PATIENT_ROUTED' event to receiving department.
        """
        # 1. Fetch & Validate Active Visit
        visit = await self.visit_service.get_visit(visit_id)
        if visit.stage != VisitStage.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Visit is no longer active.",
            )

        # 2. Fetch & Validate Target Department
        target_dept = await self.department_service.get_by_id(target_department_id)
        if not target_dept.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target department is inactive or does not exist.",
            )

        # 3. Apply Priority Escalation Rules
        # Auto-escalate return visits to prevent re-queuing behind new walk-ins
        if reason == TransferReason.RETURN_TO_DEPARTMENT and priority == QueuePriority.NORMAL:
            priority = QueuePriority.URGENT

        # 4. Safety Guardrails
        if priority == QueuePriority.CRITICAL and not (notes and notes.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A clinical justification note is required when assigning CRITICAL priority.",
            )

        async with self.db.begin_nested():
            # 5. Fetch Active Encounter & Complete It
            current_entry = await self.queue_service.get_active_queue_entry(visit_id)

            if current_entry:
                if current_entry.department_id == target_dept.dept_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Patient is already queued in the target department.",
                    )

                if current_entry.status != QueueEntryStatus.IN_PROGRESS:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Only an in-progress encounter can be transferred. "
                            "Call and start service before transferring the patient."
                        ),
                    )

                if initiated_by_staff_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="The staff member initiating the transfer is required.",
                    )

                staff_info = f" by Staff [{initiated_by_staff_id}]" if initiated_by_staff_id else ""
                completion_note = (
                    f"[{reason.value}] Transferred to {target_dept.name}{staff_info}."
                    f"{f' Notes: {notes.strip()}' if notes else ''}"
                )

                # Complete current encounter (Frees desk/clinician slot)
                await self.queue_service.complete_queue_entry(
                    current_entry.queue_entry_id,
                    staff_id=initiated_by_staff_id,
                    notes=completion_note,
                )

            # 6. Create Target Department Encounter
            new_entry = await self.queue_service.create_queue_entry(
                visit_id=visit.visit_id,
                department_id=target_dept.dept_id,
                priority=priority,
                notes=notes,
            )

            # 7. Update Visit's Current Active Queue Reference
            visit.current_queue_entry_id = new_entry.queue_entry_id
            await self.db.flush()

        new_entry = await self.queue_service.get_queue_entry(
            new_entry.queue_entry_id
        )

        # 8. Dispatch Real-time Event to Target Department
        await self.queue_service.emit_department_event(
            new_entry,
            event_type="PATIENT_ROUTED",
            extra_payload={
                "transfer_reason": reason.value,
                "source_department_id": (
                    str(current_entry.department_id) if current_entry else None
                ),
                "target_department_id": str(target_dept.dept_id),
            },
        )

        return new_entry

    async def move_patient(
        self,
        visit_id: UUID,
        target_department_id: UUID,
        priority: QueuePriority = QueuePriority.NORMAL,
        notes: Optional[str] = None,
        initiated_by_staff_id: Optional[UUID] = None,
    ) -> QueueEntry:
        """Backward-compatible alias for a standard department transfer."""
        return await self.transfer_patient(
            visit_id=visit_id,
            target_department_id=target_department_id,
            reason=TransferReason.DEPARTMENT_TRANSFER,
            priority=priority,
            notes=notes,
            initiated_by_staff_id=initiated_by_staff_id,
        )

    # ---------------------------------------------------------
    # LIVE LOCATION
    # ---------------------------------------------------------

    async def get_current_location(
        self,
        visit_id: UUID,
    ) -> dict:

        visit = await self.visit_service.get_visit(visit_id)

        active_entry = await self.queue_service.get_active_queue_entry(
            visit.visit_id
        )

        if not active_entry:
            return {
    "visit_id": visit.visit_id,
    "token_number": visit.token_number,
    "visit_stage": visit.stage.value,

    "current_queue_entry_id": None,

    "current_department_id": None,
    "current_department_name": None,

    "status": None,

    "assigned_staff_id": None,

    "position_in_line": 0,
    "estimated_wait_minutes": 0,

    "entered_at": None,
}

        department = await self.department_service.get_by_id(
            active_entry.department_id
        )

        position = await self.queue_service.get_patient_position(
            active_entry.queue_entry_id
        )

        wait = await self.queue_service.get_estimated_wait_time(
            active_entry.queue_entry_id
        )

        return {
        "visit_id": visit.visit_id,
        "token_number": visit.token_number,
        "visit_stage": visit.stage.value,
        "current_queue_entry_id": active_entry.queue_entry_id,
        "current_department_id": department.dept_id,
        "current_department_name": department.name,
        "status": active_entry.status.value,
        "assigned_staff_id": active_entry.assigned_staff_id,
        "position_in_line": position,
        "estimated_wait_minutes": wait,
        "entered_at": active_entry.entered_at.isoformat()
        if active_entry.entered_at
        else None,
}

    # ---------------------------------------------------------
    # HISTORY
    # ---------------------------------------------------------

    async def get_token_movement_history(
        self,
        visit_id: UUID,
    ) -> List[QueueEntry]:

        # Ensure the visit exists.
        await self.visit_service.get_visit(visit_id)

        stmt = (
            select(QueueEntry)
            .options(selectinload(QueueEntry.department))
            .where(QueueEntry.visit_id == visit_id)
            .order_by(QueueEntry.entered_at.asc())
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # DELEGATED QUEUE OPERATIONS
    # ---------------------------------------------------------

    async def call_queue_entry(
        self,
        queue_entry_id: UUID,
    ) -> QueueEntry:
        """
        Calls the next waiting patient via QueueService.
        WAITING -> CALLED
        """
        return await self.queue_service.call_queue_entry(queue_entry_id)

    async def start_queue_entry(
        self,
        queue_entry_id: UUID,
    ) -> QueueEntry:
        """
        Begins serving a called patient via QueueService.
        CALLED -> IN_PROGRESS
        """
        return await self.queue_service.start_queue_entry(queue_entry_id)

    async def complete_queue_entry(
        self,
        queue_entry_id: UUID,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """
        Marks current department encounter complete via QueueService.
        IN_PROGRESS -> COMPLETED
        """
        return await self.queue_service.complete_queue_entry(
            queue_entry_id, notes=notes
        )

    async def mark_no_show(
        self,
        queue_entry_id: UUID,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """
        Marks patient as no-show via QueueService.
        CALLED -> NO_SHOW
        """
        return await self.queue_service.mark_no_show(
            queue_entry_id, notes=notes
        )

    async def cancel_queue_entry(
        self,
        queue_entry_id: UUID,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """
        Cancels an active queue entry via QueueService.
        """
        return await self.queue_service.cancel_queue_entry(
            queue_entry_id, notes=notes
        )