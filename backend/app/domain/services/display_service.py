from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.models import (
    Department,
    QueueEntry,
    QueueEntryStatus,
)
from app.domain.schemas.schemas import (
    ActiveTokenDisplay,
    DepartmentDisplay,
    DisplaySnapshot,
    NextTokenDisplay,
    RecentTokenDisplay,
)
from app.domain.services.queue_service import QueueService


class DisplayService:
    """
    Read-only service responsible for building public queue-display data.

    DisplayService does not modify queue state. It aggregates information
    from departments, queue entries, visits, and QueueService into a
    presentation-agnostic DisplaySnapshot.

    The frontend decides how that snapshot is rendered depending on the
    available screen size and facility configuration.
    """

    def __init__(
        self,
        db: AsyncSession,
        facility_name: str = "HPQMS Healthcare",
    ):
        self.db = db
        self.facility_name = facility_name
        self.queue_service = QueueService(db)

    # =========================================================
    # PUBLIC SNAPSHOT
    # =========================================================

    async def get_snapshot(
        self,
        *,
        next_limit: int = 3,
        recent_limit: int = 3,
    ) -> DisplaySnapshot:
        """
        Build a complete display snapshot for all active departments.

        This is the main method consumed by public display endpoints.
        """

        if next_limit < 0:
            raise ValueError("next_limit cannot be negative.")

        if recent_limit < 0:
            raise ValueError("recent_limit cannot be negative.")

        result = await self.db.execute(
            select(Department)
            .where(Department.is_active.is_(True))
            .order_by(Department.name)
        )

        departments = result.scalars().all()

        department_displays: list[DepartmentDisplay] = []

        for department in departments:
            department_display = await self.get_department_display(
                department.dept_id,
                department_name=department.name,
                next_limit=next_limit,
                recent_limit=recent_limit,
            )

            department_displays.append(department_display)

        return DisplaySnapshot(
            facility_name=self.facility_name,
            server_timestamp=datetime.now(timezone.utc),
            departments=department_displays,
            announcements=[],
        )

    # =========================================================
    # DEPARTMENT DISPLAY
    # =========================================================

    async def get_department_display(
        self,
        dept_id: UUID,
        department_name: str | None = None,
        *,
        next_limit: int = 3,
        recent_limit: int = 3,
    ) -> DepartmentDisplay:
        """
        Build the public display state for one department.
        """

        if next_limit < 0:
            raise ValueError("next_limit cannot be negative.")

        if recent_limit < 0:
            raise ValueError("recent_limit cannot be negative.")

        if department_name is None:
            department = await self.db.get(
                Department,
                dept_id,
            )

            if department is None:
                department_name = "Unknown Department"
            else:
                department_name = department.name

        active_tokens = await self._get_active_tokens(
            dept_id
        )

        next_tokens = await self._get_next_tokens(
            dept_id,
            limit=next_limit,
        )

        recent_tokens = await self._get_recent_tokens(
            dept_id,
            limit=recent_limit,
        )

        waiting_count = await self._get_waiting_count(
            dept_id
        )

        estimated_wait = await self._get_estimated_wait(
            dept_id
        )

        return DepartmentDisplay(
            dept_id=dept_id,
            department_name=department_name,
            active_tokens=active_tokens,
            next_tokens=next_tokens,
            recent_tokens=recent_tokens,
            waiting_count=waiting_count,
            estimated_wait_minutes=estimated_wait,
        )

    # =========================================================
    # ACTIVE TOKENS
    # =========================================================

    async def _get_active_tokens(
        self,
        dept_id: UUID,
    ) -> list[ActiveTokenDisplay]:
        """
        Return tokens currently being called or processed.

        WAITING tokens are deliberately excluded because they belong
        to the 'up next' portion of the public display.
        """

        result = await self.db.execute(
            select(QueueEntry)
            .options(selectinload(QueueEntry.visit))
            .where(
                QueueEntry.dept_id == dept_id,
                QueueEntry.status.in_(
                    (
                        QueueEntryStatus.CALLED,
                        QueueEntryStatus.IN_PROGRESS,
                    )
                ),
            )
            .order_by(
                QueueEntry.called_at.desc()
            )
        )

        entries = result.scalars().all()

        return [
            ActiveTokenDisplay(
                token_number=entry.visit.token_number,
                service_point=None,
                status=entry.status,
                called_at=entry.called_at,
            )
            for entry in entries
            if entry.visit is not None
        ]

    # =========================================================
    # NEXT TOKENS
    # =========================================================

    async def _get_next_tokens(
        self,
        dept_id: UUID,
        *,
        limit: int = 3,
    ) -> list[NextTokenDisplay]:
        """
        Return upcoming WAITING tokens.

        Queue ordering must remain consistent with the queue domain
        rules: priority first, then sequence number.
        """

        if limit == 0:
            return []

        result = await self.db.execute(
            select(QueueEntry)
            .options(selectinload(QueueEntry.visit))
            .where(
                QueueEntry.dept_id == dept_id,
                QueueEntry.status == QueueEntryStatus.WAITING,
            )
            .order_by(
                QueueEntry.priority.desc(),
                QueueEntry.sequence_number.asc(),
            )
            .limit(limit)
        )

        entries = result.scalars().all()

        return [
            NextTokenDisplay(
                token_number=entry.visit.token_number
            )
            for entry in entries
            if entry.visit is not None
        ]

    # =========================================================
    # RECENT TOKENS
    # =========================================================

    async def _get_recent_tokens(
        self,
        dept_id: UUID,
        *,
        limit: int = 3,
    ) -> list[RecentTokenDisplay]:
        """
        Return recently completed tokens.
        """

        if limit == 0:
            return []

        result = await self.db.execute(
            select(QueueEntry)
            .options(selectinload(QueueEntry.visit))
            .where(
                QueueEntry.dept_id == dept_id,
                QueueEntry.status == QueueEntryStatus.COMPLETED,
            )
            .order_by(
                QueueEntry.completed_at.desc()
            )
            .limit(limit)
        )

        entries = result.scalars().all()

        return [
            RecentTokenDisplay(
                token_number=entry.visit.token_number
            )
            for entry in entries
            if entry.visit is not None
        ]

    # =========================================================
    # WAITING COUNT
    # =========================================================

    async def _get_waiting_count(
        self,
        dept_id: UUID,
    ) -> int:
        """
        Return the number of patients currently waiting in a department.
        """

        result = await self.db.execute(
            select(
                func.count(QueueEntry.queue_entry_id)
            )
            .where(
                QueueEntry.dept_id == dept_id,
                QueueEntry.status == QueueEntryStatus.WAITING,
            )
        )

        return result.scalar_one() or 0

    # =========================================================
    # ESTIMATED WAIT
    # =========================================================

    async def _get_estimated_wait(
        self,
        dept_id: UUID,
    ) -> int | None:
        """
        Calculate estimated waiting time for the next patient.

        QueueService remains responsible for the actual wait-time
        calculation. DisplayService only exposes the result.
        """

        result = await self.db.execute(
            select(QueueEntry.queue_entry_id)
            .where(
                QueueEntry.dept_id == dept_id,
                QueueEntry.status == QueueEntryStatus.WAITING,
            )
            .order_by(
                QueueEntry.priority.desc(),
                QueueEntry.sequence_number.asc(),
            )
            .limit(1)
        )

        next_entry_id = result.scalar_one_or_none()

        if next_entry_id is None:
            return 0

        return await self.queue_service.get_estimated_wait_time(
            next_entry_id
        )