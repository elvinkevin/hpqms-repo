import zoneinfo
from datetime import date, datetime, timezone
from typing import Final, List, Optional
from uuid import UUID

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
    Visit,
)

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
        department_id: UUID,
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
        department = await self.db.get(Department, department_id)
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department {department_id} not found.",
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
                department_id=department_id,
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
            department_id=department_id,
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

    async def get_department_queue(self, department_id: UUID) -> List[QueueEntry]:
        """Retrieves active records for a department."""
        stmt = (
            select(QueueEntry)
            .options(selectinload(QueueEntry.visit).selectinload(Visit.patient))
            .where(
                and_(
                    QueueEntry.department_id == department_id,
                    QueueEntry.status.in_(ACTIVE_STATUSES),
                )
            )
            .order_by(PRIORITY_DB_ORDER, QueueEntry.sequence_number.asc())
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
        department_id: UUID,
    ) -> QueueEntry | None:
        """Returns the next patient waiting to be called in a department."""
        today_local = datetime.now(CLINIC_TZ).date()

        stmt = (
            select(QueueEntry)
            .options(selectinload(QueueEntry.visit).selectinload(Visit.patient))
            .where(
                and_(
                    QueueEntry.department_id == department_id,
                    QueueEntry.status == QueueEntryStatus.WAITING,
                    func.cast(QueueEntry.entered_at, Date) == today_local,
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
        """Validate and apply a queue state transition.

        The transaction is owned by the caller. This method only mutates
        and flushes the database state. WebSocket events must be emitted
        after the transaction commits in the route/caller handler.
        """

        entry = await self.db.get(
            QueueEntry,
            queue_entry_id,
            options=[
                selectinload(QueueEntry.visit).options(
                    selectinload(Visit.patient)
                ),
                selectinload(QueueEntry.department),
            ],
        )

        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Queue entry {queue_entry_id} not found.",
            )

        allowed = VALID_TRANSITIONS.get(entry.status, set())

        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid state transition requested: "
                    f"{entry.status} -> {new_status}."
                ),
            )

        self._apply_status_updates(
            entry,
            new_status,
            staff_id,
            notes,
        )

        self._apply_lifecycle_timestamps(
            entry,
            new_status,
        )

        await self.db.flush()

        
        stmt = (
            select(QueueEntry)
            .options(
                selectinload(QueueEntry.visit).options(
                    selectinload(Visit.patient)
                ),
                selectinload(QueueEntry.department),
            )
            .where(QueueEntry.queue_entry_id == entry.queue_entry_id)
        )

        refreshed = await self.db.execute(stmt)
        return refreshed.scalar_one()

    def _apply_status_updates(
        self,
        entry: QueueEntry,
        new_status: QueueEntryStatus,
        staff_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Mutates status, assigned staff, and notes on the entry instance."""
        entry.status = new_status
        if staff_id is not None and hasattr(entry, "assigned_staff_id"):
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
    # DISPLAY BROADCAST (PUBLIC SEPARATE METHOD)
    # ------------------------------------------------------------------

    async def emit_display_event(
        self,
        entry: QueueEntry,
        new_status: Optional[QueueEntryStatus] = None,
    ) -> None:
        """Publish the display event after the transaction has committed."""
        if new_status is None:
            new_status = getattr(entry, "status", None)

        if new_status is None:
            return

        department_id = str(entry.department_id)
        token_number = entry.visit.token_number if entry.visit else None

        if not token_number:
            return

        department_name = entry.department.name if entry.department else None

        if new_status == QueueEntryStatus.CALLED:
            await ws_manager.broadcast_token_called(
                department_id=department_id,
                token_number=token_number,
                service_point=None,
                occurred_at=getattr(entry, "called_at", None),
                department_name=department_name,
                message=f"Token {token_number} called to service",
                priority="HIGH",
            )
        elif new_status == QueueEntryStatus.IN_PROGRESS:
            await ws_manager.broadcast_queue_updated(
                department_id=department_id,
                department_name=department_name,
                message=f"Token {token_number} is now in service",
                priority="NORMAL",
            )
        elif new_status == QueueEntryStatus.COMPLETED:
            await ws_manager.broadcast_token_completed(
                department_id=department_id,
                token_number=token_number,
                occurred_at=getattr(entry, "completed_at", None),
                department_name=department_name,
                message=f"Token {token_number} completed",
                priority="NORMAL",
            )
        elif new_status == QueueEntryStatus.CANCELLED:
            await ws_manager.broadcast_token_cancelled(
                department_id=department_id,
                token_number=token_number,
                occurred_at=getattr(entry, "completed_at", None),
                department_name=department_name,
                message=f"Token {token_number} cancelled",
                priority="NORMAL",
            )
        elif new_status in {QueueEntryStatus.NO_SHOW, QueueEntryStatus.WAITING}:
            await ws_manager.broadcast_queue_updated(
                department_id=department_id,
                department_name=department_name,
                message=f"Queue updated for token {token_number}",
                priority="NORMAL",
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
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Transitions IN_PROGRESS -> COMPLETED."""
        return await self.transition_entry_status(
            queue_entry_id, QueueEntryStatus.COMPLETED, notes=notes
        )

    async def mark_no_show(
        self,
        queue_entry_id: UUID,
        notes: Optional[str] = None,
    ) -> QueueEntry:
        """Transitions CALLED -> NO_SHOW."""
        return await self.transition_entry_status(
            queue_entry_id, QueueEntryStatus.NO_SHOW, notes=notes
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
                    QueueEntry.department_id == target.department_id,
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
        department_id: UUID,
    ) -> List[QueueEntry]:
        """Returns NO_SHOW entries for a department."""
        stmt = (
            select(QueueEntry)
            .options(
                selectinload(QueueEntry.visit).selectinload(Visit.patient),
                selectinload(QueueEntry.department),
            )
            .where(
                and_(
                    QueueEntry.department_id == department_id,
                    QueueEntry.status == QueueEntryStatus.NO_SHOW,
                )
            )
            .order_by(
                QueueEntry.completed_at.desc(),
                QueueEntry.sequence_number.asc(),
            )
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())