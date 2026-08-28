import zoneinfo
from datetime import date, datetime, timezone
from typing import Any, Final, List, Mapping, Optional
from uuid import UUID, uuid4

from asyncpg.exceptions import UniqueViolationError
from fastapi import HTTPException, status
from sqlalchemy import Date, and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.routes.websocket_manager import ws_manager
from app.domain.models.models import (
    Department,
    DepartmentQueueCounter,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    Staff,
    StaffRole,
    Visit,
)
from app.domain.schemas.schemas import CurrentUser

CLINIC_TZ: Final = zoneinfo.ZoneInfo("Africa/Nairobi")

# Priority matrix configurations
PRIORITY_ORDER: Final = {
    QueuePriority.CRITICAL: 0,
    QueuePriority.URGENT: 1,
    QueuePriority.SEMI_URGENT: 2,
    QueuePriority.NORMAL: 3,
}

PRIORITY_DB_ORDER: Final = case(
    (QueuePriority.CRITICAL == QueueEntry.priority, PRIORITY_ORDER[QueuePriority.CRITICAL]),
    (QueuePriority.URGENT == QueueEntry.priority, PRIORITY_ORDER[QueuePriority.URGENT]),
    (QueuePriority.SEMI_URGENT == QueueEntry.priority, PRIORITY_ORDER[QueuePriority.SEMI_URGENT]),
    (QueuePriority.NORMAL == QueueEntry.priority, PRIORITY_ORDER[QueuePriority.NORMAL]),
    else_=99,
)

ACTIVE_STATUSES: Final = [
    QueueEntryStatus.WAITING,
    QueueEntryStatus.CALLED,
    QueueEntryStatus.IN_PROGRESS,
]

VALID_TRANSITIONS: Final = {
    QueueEntryStatus.WAITING: frozenset({QueueEntryStatus.CALLED, QueueEntryStatus.CANCELLED}),
    QueueEntryStatus.CALLED: frozenset({QueueEntryStatus.IN_PROGRESS, QueueEntryStatus.WAITING, QueueEntryStatus.NO_SHOW, QueueEntryStatus.CANCELLED}),
    QueueEntryStatus.IN_PROGRESS: frozenset({QueueEntryStatus.COMPLETED, QueueEntryStatus.CANCELLED}),
    QueueEntryStatus.COMPLETED: frozenset(),
    QueueEntryStatus.NO_SHOW: frozenset({QueueEntryStatus.WAITING}),
    QueueEntryStatus.CANCELLED: frozenset(),
}

AVG_CONSULT_MINUTES: Final = 8


class QueueService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # CREATE QUEUE ENTRY
    # ------------------------------------------------------------------

    async def create_queue_entry(
        self,
        visit_id: UUID,
        dept_id: UUID,
        priority: QueuePriority = QueuePriority.NORMAL,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Creates an atomic queue entry step using the DepartmentQueueCounter ledger."""
        # 1. Validate Visit exists
        visit = await self.db.get(Visit, visit_id)
        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Visit {visit_id} not found.",
            )

        # 2. Validate Department exists
        department = await self.db.get(Department, dept_id)
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department {dept_id} not found.",
            )

        # 3. Check for active queue entry on this visit
        active_entry = await self.get_active_queue_entry(visit_id)
        if active_entry:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Visit {visit_id} already has an active queue entry.",
            )

        today_local = datetime.now(CLINIC_TZ).date()

        # 4. Increment sequence
        stmt = (
            insert(DepartmentQueueCounter)
            .values(
                dept_id=dept_id,
                queue_date=today_local,
                last_sequence=1,
            )
            .on_conflict_do_update(
                constraint="uq_dept_queue_date",
                set_={
                    "last_sequence": DepartmentQueueCounter.last_sequence + 1
                },
            )
            .returning(DepartmentQueueCounter.last_sequence)
        )

        result = await self.db.execute(stmt)
        assigned_sequence = result.scalar_one()

        # 5. Insert queue entry
        new_entry = QueueEntry(
            visit_id=visit_id,
            dept_id=dept_id,
            sequence_number=assigned_sequence,
            priority=priority,
            status=QueueEntryStatus.WAITING,
            notes=notes,
        )

        self.db.add(new_entry)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active queue entry already exists for this visit.",
            ) from exc

        await self.db.refresh(new_entry)
        return new_entry

    # ------------------------------------------------------------------
    # READ OPERATIONS
    # ------------------------------------------------------------------

    async def get_department_queue(
        self,
        dept_id: UUID,
    ) -> List[QueueEntry]:
        """Retrieves active queue records for a department for today."""

        today_local = datetime.now(CLINIC_TZ).date()

        stmt = (
            select(QueueEntry)
            .options(
                selectinload(QueueEntry.visit)
                .selectinload(Visit.patient)
            )
            .where(
                and_(
                    QueueEntry.dept_id == dept_id,
                    QueueEntry.status.in_(ACTIVE_STATUSES),
                    func.cast(QueueEntry.entered_at, Date) == today_local,
                )
            )
            .order_by(
                PRIORITY_DB_ORDER,
                QueueEntry.sequence_number.asc(),
            )
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def get_active_queue_entry(self, visit_id: UUID) -> QueueEntry | None:
        """Returns the active queue step running for an active visit encounter."""
        stmt = (
            select(QueueEntry)
            .where(
                and_(
                    QueueEntry.visit_id == visit_id,
                    QueueEntry.status.in_(ACTIVE_STATUSES),
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_queue_entry(
        self,
        queue_entry_id: UUID,
    ) -> QueueEntry:
        """Retrieves a single queue entry with relations."""
        stmt = (
            select(QueueEntry)
            .options(
                selectinload(QueueEntry.visit).selectinload(Visit.patient),
                selectinload(QueueEntry.department),
            )
            .where(QueueEntry.queue_entry_id == queue_entry_id)
        )

        result = await self.db.execute(stmt)
        entry = result.scalar_one_or_none()

        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Queue entry not found.",
            )

        return entry

    async def get_next_patient(
        self,
        dept_id: UUID,
    ) -> QueueEntry | None:
        """Returns the highest-priority waiting patient in a department."""

        stmt = (
            select(QueueEntry)
            .options(
                selectinload(QueueEntry.visit)
                .selectinload(Visit.patient)
            )
            .where(
                and_(
                    QueueEntry.dept_id == dept_id,
                    QueueEntry.status == QueueEntryStatus.WAITING,
                )
            )
            .order_by(
                PRIORITY_DB_ORDER,
                QueueEntry.sequence_number.asc(),
            )
            .limit(1)
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # STATE TRANSITIONS ENGINE
    # ------------------------------------------------------------------

    async def transition_entry_status(
        self,
        queue_entry_id: UUID,
        new_status: QueueEntryStatus,
        staff_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Validate and apply a queue state transition."""

        # 1. Fetch entry with row lock & eager loads upfront
        stmt = (
            select(QueueEntry)
            .options(
                selectinload(QueueEntry.visit).selectinload(Visit.patient),
                selectinload(QueueEntry.department),
            )
            .where(QueueEntry.queue_entry_id == queue_entry_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        entry = result.scalar_one_or_none()

        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Queue entry {queue_entry_id} not found.",
            )

        # ---------------------------------------------------------
        # DEPARTMENT ISOLATION GUARD
        # ---------------------------------------------------------
        if staff_id is not None:
            staff_stmt = select(Staff).where(Staff.staff_id == staff_id)
            staff_result = await self.db.execute(staff_stmt)
            acting_staff = staff_result.scalar_one_or_none()

            if acting_staff and acting_staff.role != StaffRole.ADMIN:
                if acting_staff.dept_id != entry.dept_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cannot operate on queue entries outside your assigned department.",
                    )

        # ---------------------------------------------------------
        # STATE TRANSITION VALIDATION
        # ---------------------------------------------------------
        allowed = VALID_TRANSITIONS.get(entry.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid state transition requested: "
                    f"{entry.status} -> {new_status}."
                ),
            )

        # ---------------------------------------------------------
        # STAFF OWNERSHIP / CLAIM VALIDATION
        # ---------------------------------------------------------

        if new_status == QueueEntryStatus.CALLED:
            if staff_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A staff member is required to call a patient.",
                )

            if entry.assigned_staff_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This queue entry is already assigned to a staff member.",
                )

            active_staff_stmt = (
                select(QueueEntry.queue_entry_id)
                .where(
                    QueueEntry.assigned_staff_id == staff_id,
                    QueueEntry.status.in_(
                        {
                            QueueEntryStatus.CALLED,
                            QueueEntryStatus.IN_PROGRESS,
                        }
                    ),
                )
                .limit(1)
            )
            active_staff_result = await self.db.execute(active_staff_stmt)
            if active_staff_result.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "You already have an active patient. "
                        "Complete or release the current patient before "
                        "calling another patient."
                    ),
                )

        elif new_status == QueueEntryStatus.IN_PROGRESS:
            if staff_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A staff member is required to start a patient.",
                )
            if entry.assigned_staff_id != staff_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You cannot start this patient because the patient is assigned to another staff member.",
                )

        elif new_status == QueueEntryStatus.COMPLETED:
            if staff_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A staff member is required to complete a patient.",
                )
            if entry.assigned_staff_id != staff_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You cannot complete this patient because the patient is assigned to another staff member.",
                )

        elif new_status == QueueEntryStatus.NO_SHOW:
            if staff_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A staff member is required to mark a patient as no-show.",
                )
            if entry.assigned_staff_id is not None and entry.assigned_staff_id != staff_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You cannot mark this patient as no-show because the patient is assigned to another staff member.",
                )
        # ---------------------------------------------------------
        # APPLY CHANGES & REFLECT STATE
        # ---------------------------------------------------------
        self._apply_status_updates(entry, new_status, staff_id, notes)
        self._apply_lifecycle_timestamps(entry, new_status)

        await self.db.flush()
        return entry

    def _apply_status_updates(
        self,
        entry: QueueEntry,
        new_status: QueueEntryStatus,
        staff_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> None:

        entry.status = new_status

        if new_status == QueueEntryStatus.WAITING:
            entry.assigned_staff_id = None

        elif staff_id is not None and hasattr(entry, "assigned_staff_id"):
            entry.assigned_staff_id = staff_id

        if notes is not None:
            entry.notes = notes

    def _apply_lifecycle_timestamps(
        self,
        entry: QueueEntry,
        new_status: QueueEntryStatus,
    ) -> None:
        """Sets lifecycle timestamps based on target state."""

        now = datetime.now(timezone.utc)

        if new_status == QueueEntryStatus.CALLED:
            entry.called_at = now

        elif new_status == QueueEntryStatus.IN_PROGRESS:
            if not getattr(entry, "called_at", None):
                entry.called_at = now

            if hasattr(entry, "started_at"):
                entry.started_at = now

        elif new_status == QueueEntryStatus.COMPLETED:
            if hasattr(entry, "completed_at"):
                entry.completed_at = now

        elif new_status == QueueEntryStatus.CANCELLED:
            if hasattr(entry, "completed_at"):
                entry.completed_at = now

        elif new_status == QueueEntryStatus.NO_SHOW:
            if hasattr(entry, "no_show_at"):
                entry.no_show_at = now

    # ------------------------------------------------------------------
    # DISPLAY BROADCAST
    # ------------------------------------------------------------------

    async def emit_display_event(
        self,
        entry: QueueEntry,
        new_status: Optional[QueueEntryStatus] = None,
        event_type: Optional[str] = None,
    ) -> None:
        """
        Publish a canonical display event after the transaction has committed.

        The route layer is responsible for committing the database transaction
        before calling this method.

        Args:
            entry:
                QueueEntry containing the final persisted state.

            new_status:
                Optional status override. Normally the current entry.status
                is used.

            event_type:
                Optional explicit event type. This is primarily used for
                operations such as requeue where the final status alone
                cannot identify the action that occurred.
        """

        if new_status is None:
            new_status = getattr(entry, "status", None)

        if new_status is None:
            return

        dept_id = str(entry.dept_id)

        token_number = (
            entry.visit.token_number
            if entry.visit is not None
            else None
        )

        if not token_number:
            return

        department_name = (
            entry.department.name
            if entry.department is not None
            else None
        )

        queue_priority = (
            entry.priority.value
            if entry.priority is not None
            else None
        )

        assigned_staff_id = (
            str(entry.assigned_staff_id)
            if entry.assigned_staff_id is not None
            else None
        )

        # --------------------------------------------------------------
        # DETERMINE EVENT TYPE
        # --------------------------------------------------------------

        if event_type is None:
            event_type_map = {
                QueueEntryStatus.CALLED: "TOKEN_CALLED",
                QueueEntryStatus.IN_PROGRESS: "TOKEN_SERVICE_STARTED",
                QueueEntryStatus.COMPLETED: "TOKEN_COMPLETED",
                QueueEntryStatus.NO_SHOW: "TOKEN_NO_SHOW",
                QueueEntryStatus.CANCELLED: "TOKEN_CANCELLED",
            }

            event_type = event_type_map.get(new_status)

        # WAITING is intentionally not mapped automatically.
        #
        # A WAITING entry could simply already be waiting, whereas a
        # NO_SHOW -> WAITING transition specifically represents a requeue.
        if event_type is None:
            return

        # --------------------------------------------------------------
        # DETERMINE DOMAIN OCCURRENCE TIME
        # --------------------------------------------------------------

        occurred_at = None

        if new_status == QueueEntryStatus.CALLED:
            occurred_at = getattr(entry, "called_at", None)

        elif new_status == QueueEntryStatus.IN_PROGRESS:
            occurred_at = getattr(entry, "started_at", None)

        elif new_status == QueueEntryStatus.COMPLETED:
            occurred_at = getattr(entry, "completed_at", None)

        elif new_status == QueueEntryStatus.NO_SHOW:
            occurred_at = getattr(entry, "no_show_at", None)

        elif new_status == QueueEntryStatus.CANCELLED:
            occurred_at = getattr(entry, "completed_at", None)

        # Requeue does not currently have its own lifecycle timestamp.
        if occurred_at is None:
            occurred_at = datetime.now(timezone.utc)

        # --------------------------------------------------------------
        # EVENT PRIORITY
        # --------------------------------------------------------------

        event_priority = "NORMAL"

        if event_type == "TOKEN_CALLED":
            event_priority = "HIGH"

        # --------------------------------------------------------------
        # CANONICAL EVENT PAYLOAD
        # --------------------------------------------------------------

        payload = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "priority": event_priority,

            "queue_entry_id": str(entry.queue_entry_id),
            "dept_id": dept_id,
            "department_name": department_name,

            "token_number": token_number,

            "status": new_status.value,
            "queue_priority": queue_priority,

            "assigned_staff_id": assigned_staff_id,

            "occurred_at": occurred_at.isoformat(),
            "server_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await ws_manager.broadcast_display(
            payload,
            dept_id=dept_id,
        )

    # --- Specific Transition Callables ---

    async def call_queue_entry(
        self,
        queue_entry_id: UUID,
        staff_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Transitions WAITING -> CALLED."""
        return await self.transition_entry_status(
            queue_entry_id, QueueEntryStatus.CALLED, staff_id=staff_id, notes=notes
        )

    async def start_queue_entry(
        self,
        queue_entry_id: UUID,
        staff_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Transitions CALLED -> IN_PROGRESS."""
        return await self.transition_entry_status(
            queue_entry_id, QueueEntryStatus.IN_PROGRESS, staff_id=staff_id, notes=notes
        )

    async def complete_queue_entry(
        self,
        queue_entry_id: UUID,
        staff_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        return await self.transition_entry_status(
            queue_entry_id=queue_entry_id,
            new_status=QueueEntryStatus.COMPLETED,
            staff_id=staff_id,
            notes=notes,
        )

    async def mark_no_show(
        self,
        queue_entry_id: UUID,
        staff_id: UUID,  # <-- Add staff_id
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Transitions CALLED -> NO_SHOW for staff-owned entries."""
        return await self.transition_entry_status(
            queue_entry_id=queue_entry_id,
            new_status=QueueEntryStatus.NO_SHOW,
            staff_id=staff_id,  # <-- Pass staff_id
            notes=notes,
        )

    async def cancel_queue_entry(
        self,
        queue_entry_id: UUID,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Transitions ANY ACTIVE -> CANCELLED."""
        return await self.transition_entry_status(
            queue_entry_id, QueueEntryStatus.CANCELLED, notes=notes
        )

    # --- Backward-Compatibility Aliases ---

    async def call_patient(
        self, queue_entry_id: UUID, staff_id: Optional[UUID] = None, notes: Optional[str] = None
    ) -> QueueEntry:
        return await self.call_queue_entry(queue_entry_id, staff_id=staff_id, notes=notes)

    async def start_patient(
        self, queue_entry_id: UUID, staff_id: Optional[UUID] = None, notes: Optional[str] = None
    ) -> QueueEntry:
        return await self.start_queue_entry(queue_entry_id, staff_id=staff_id, notes=notes)

    async def start_consultation(
        self, queue_entry_id: UUID, staff_id: Optional[UUID] = None, notes: Optional[str] = None
    ) -> QueueEntry:
        """Alias for starting a consultation/entry (CALLED -> IN_PROGRESS)."""
        return await self.start_queue_entry(queue_entry_id, staff_id=staff_id, notes=notes)

    # ------------------------------------------------------------------
    # ANALYTICS & LINE METRICS ENGINE
    # ------------------------------------------------------------------

    async def get_patient_position(self, queue_entry_id: UUID) -> int:
        """Evaluates patient queue position within active statuses."""
        target = await self.db.get(QueueEntry, queue_entry_id)
        if not target or target.status not in ACTIVE_STATUSES:
            return 0

        target_priority_val = PRIORITY_ORDER.get(target.priority, 99)

        stmt = (
            select(func.count(QueueEntry.queue_entry_id))
            .where(
                and_(
                    QueueEntry.dept_id == target.dept_id,
                    QueueEntry.status.in_(ACTIVE_STATUSES),
                    or_(
                        PRIORITY_DB_ORDER < target_priority_val,
                        and_(
                            PRIORITY_DB_ORDER == target_priority_val,
                            QueueEntry.sequence_number < target.sequence_number,
                        ),
                    ),
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one() + 1

    async def get_estimated_wait_time(self, queue_entry_id: UUID) -> int:
        """Returns estimated wait time in minutes."""
        position_ahead = await self.get_patient_position(queue_entry_id) - 1
        return max(position_ahead * AVG_CONSULT_MINUTES, 0)

    async def get_department_no_show_queue(
        self,
        dept_id: UUID,
        staff_id: UUID,
    ) -> List[QueueEntry]:
        """Returns NO_SHOW entries assigned to the authenticated staff member."""

        stmt = (
            select(QueueEntry)
            .options(
                selectinload(QueueEntry.visit).selectinload(Visit.patient),
                selectinload(QueueEntry.department),
            )
            .where(
                and_(
                    QueueEntry.dept_id == dept_id,
                    QueueEntry.status == QueueEntryStatus.NO_SHOW,
                    QueueEntry.assigned_staff_id == staff_id,
                )
            )
            .order_by(
                QueueEntry.completed_at.desc(),
                QueueEntry.sequence_number.asc(),
            )
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def requeue_queue_entry(
        self,
        queue_entry_id: UUID,
        staff_id: UUID,
    ) -> QueueEntry:

        stmt = (
                select(QueueEntry)
                .options(
                    selectinload(QueueEntry.visit),
                    selectinload(QueueEntry.department),
                )
                .where(QueueEntry.queue_entry_id == queue_entry_id)
            )

        result = await self.db.execute(stmt)
        entry = result.scalar_one_or_none()

        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Queue entry {queue_entry_id} not found.",
            )

        if entry.status != QueueEntryStatus.NO_SHOW:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only NO_SHOW entries can be requeued.",
            )

        if entry.assigned_staff_id != staff_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only requeue patients assigned to you.",
            )

        entry.status = QueueEntryStatus.WAITING
        entry.assigned_staff_id = None

        await self.db.flush()

        return entry

    async def emit_department_event(
        self,
        entry: QueueEntry,
        event_type: str,
        extra_payload: Mapping[str, Any] | None = None,
    ) -> None:
        dept_id = str(entry.dept_id)

        # Extract relationship attributes safely with fallbacks
        token_number = (
            entry.visit.token_number
            if hasattr(entry, "visit") and entry.visit is not None
            else getattr(entry, "token_number", None)
        )

        department_name = (
            entry.department.name
            if hasattr(entry, "department") and entry.department is not None
            else None
        )

        queue_priority = (
            entry.priority.value
            if hasattr(entry, "priority") and entry.priority is not None
            else getattr(entry, "priority", None)
        )

        status_val = (
            entry.status.value
            if hasattr(entry.status, "value")
            else entry.status
        )

        payload = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "priority": "NORMAL",
            "queue_entry_id": str(entry.queue_entry_id),
            "dept_id": dept_id,
            "department_name": department_name,
            "token_number": token_number,
            "status": status_val,
            "queue_priority": queue_priority,
            "assigned_staff_id": (
                str(entry.assigned_staff_id)
                if entry.assigned_staff_id
                else None
            ),
            "server_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if extra_payload:
            payload.update(extra_payload)

        await ws_manager.broadcast_department(
            payload,
            dept_id=dept_id,
        )
