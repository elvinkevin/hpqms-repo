from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import Depends

from app.db.session import get_db
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.models import (
    Appointment,
    AppointmentStatus,
    AuditLog,
    Department,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    ServicePoint,
    Staff,
    Visit,
    VisitStage,
)


ACTIVE_QUEUE_STATUSES = (
    QueueEntryStatus.WAITING,
    QueueEntryStatus.CALLED,
    QueueEntryStatus.IN_PROGRESS,
)


class AdminService:
    """
    Read-only aggregation layer for the admin dashboard.

    Responsibilities:
        • Hospital-wide live overview (queues, staff, traffic)
        • Department-by-department queue snapshots

    This service deliberately performs no writes. All queries run against
    existing tables, so no migrations are required by the dashboard itself.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @classmethod
    def get_instance(
        cls,
        db: AsyncSession = Depends(get_db),
    ) -> "AdminService":
        """FastAPI dependency providing an AdminService instance."""
        return cls(db)

    # ---------------------------------------------------------
    # LIVE OVERVIEW
    # ---------------------------------------------------------

    async def get_overview(self) -> dict:
        """
        Single hospital-wide snapshot for the admin dashboard landing page.

        Returns:
            {
                "generated_at": iso8601,
                "totals": {waiting, called, in_progress, active_visits,
                           patients, staff_active, staff_on_duty,
                           appointments_today},
                "critical_waiting": int,
                "departments": [ {dept_id, name, code, type, is_active,
                                  waiting, called, in_progress,
                                  staff_on_duty, max_capacity} ],
                "on_duty_staff": [ {staff_id, name, role, dept_id,
                                    department, service_point_id} ],
            }
        """
        today = date.today()

        # ---- Hospital-wide queue status counts --------------------------
        status_counts_result = await self.db.execute(
            select(
                QueueEntry.status,
                func.count(QueueEntry.queue_entry_id),
            )
            .where(QueueEntry.status.in_(ACTIVE_QUEUE_STATUSES))
            .group_by(QueueEntry.status)
        )
        status_counts = {
            row[0]: row[1] for row in status_counts_result.all()
        }

        # ---- Critical/urgent patients still waiting ---------------------
        critical_waiting_result = await self.db.execute(
            select(func.count(QueueEntry.queue_entry_id))
            .where(
                QueueEntry.status == QueueEntryStatus.WAITING,
                QueueEntry.priority.in_(
                    (QueuePriority.URGENT, QueuePriority.CRITICAL)
                ),
            )
        )
        critical_waiting = critical_waiting_result.scalar_one()

        # ---- Active visits ----------------------------------------------
        active_visits_result = await self.db.execute(
            select(func.count(Visit.visit_id))
            .where(Visit.stage == VisitStage.ACTIVE)
        )
        active_visits = active_visits_result.scalar_one()

        # ---- Registered patients ----------------------------------------
        patients_result = await self.db.execute(
            select(func.count(Patient.patient_id))
            .where(Patient.is_active == True)  # noqa: E712
        )
        total_patients = patients_result.scalar_one()

        # ---- Staff counts ------------------------------------------------
        staff_result = await self.db.execute(
            select(
                func.count(Staff.staff_id),
                func.count(
                    case((Staff.is_on_duty == True, 1))  # noqa: E712
                ),
            )
            .where(Staff.is_active == True)  # noqa: E712
        )
        staff_total, staff_on_duty = staff_result.one()

        # ---- Appointments today ------------------------------------------
        appointments_result = await self.db.execute(
            select(func.count(Appointment.appointment_id)).where(
                func.date(Appointment.appointment_date) == today,
                Appointment.status == AppointmentStatus.SCHEDULED,
            )
        )
        appointments_today = appointments_result.scalar_one()

        # ---- Per-department queue snapshot --------------------------------
        dept_rows = (
            select(
                Department.dept_id,
                Department.name,
                Department.department_code,
                Department.type,
                Department.is_active,
                Department.max_capacity,
                QueueEntry.status,
                QueueEntry.priority,
                func.count(QueueEntry.queue_entry_id).label("entry_count"),
            )
            .outerjoin(
                QueueEntry,
                (QueueEntry.dept_id == Department.dept_id)
                & (QueueEntry.status.in_(ACTIVE_QUEUE_STATUSES)),
            )
            .group_by(
                Department.dept_id,
                Department.name,
                Department.department_code,
                Department.type,
                Department.is_active,
                Department.max_capacity,
                QueueEntry.status,
                QueueEntry.priority,
            )
            .order_by(Department.name)
        )
        dept_result = await self.db.execute(dept_rows)

        departments: dict[UUID, dict] = {}
        critical_by_dept: dict[UUID, int] = {}
        for row in dept_result.all():
            (
                dept_id, name, code, dept_type, is_active,
                max_capacity, status, priority, count,
            ) = row

            bucket = departments.setdefault(
                dept_id,
                {
                    "dept_id": dept_id,
                    "name": name,
                    "code": code,
                    "type": dept_type.value if hasattr(dept_type, "value") else dept_type,
                    "is_active": is_active,
                    "max_capacity": max_capacity,
                    "waiting": 0,
                    "called": 0,
                    "in_progress": 0,
                    "critical_waiting": 0,
                    "staff_on_duty": 0,
                },
            )

            if status is None:
                # Department with no active queue entries (outer join null row)
                continue

            key = {
                QueueEntryStatus.WAITING: "waiting",
                QueueEntryStatus.CALLED: "called",
                QueueEntryStatus.IN_PROGRESS: "in_progress",
            }.get(status)

            if key:
                bucket[key] += count

            if (
                status == QueueEntryStatus.WAITING
                and priority in (QueuePriority.URGENT, QueuePriority.CRITICAL)
            ):
                bucket["critical_waiting"] += count
                critical_by_dept[dept_id] = (
                    critical_by_dept.get(dept_id, 0) + count
                )

        # ---- On-duty staff per department ---------------------------------
        duty_result = await self.db.execute(
            select(Staff.dept_id, func.count(Staff.staff_id))
            .where(
                Staff.is_active == True,  # noqa: E712
                Staff.is_on_duty == True,  # noqa: E712
            )
            .group_by(Staff.dept_id)
        )
        duty_by_dept = {row[0]: row[1] for row in duty_result.all()}
        for dept_id, bucket in departments.items():
            bucket["staff_on_duty"] = duty_by_dept.get(dept_id, 0)

        # ---- On-duty staff detail (for the live roster panel) --------------
        roster_result = await self.db.execute(
            select(Staff, ServicePoint)
            .outerjoin(
                ServicePoint,
                ServicePoint.service_point_id == Staff.active_service_point_id,
            )
            .where(
                Staff.is_active == True,  # noqa: E712
                Staff.is_on_duty == True,  # noqa: E712
            )
            .order_by(Staff.last_name, Staff.first_name)
        )
        on_duty_staff = [
            {
                "staff_id": staff.staff_id,
                "employee_id": staff.employee_id,
                "full_name": f"{staff.first_name} {staff.last_name}",
                "role": staff.role.value,
                "dept_id": staff.dept_id,
                "service_point_id": (
                    sp.service_point_id if sp is not None else None
                ),
                "service_point_label": sp.label if sp is not None else None,
            }
            for staff, sp in roster_result.all()
        ]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "waiting": status_counts.get(QueueEntryStatus.WAITING, 0),
                "called": status_counts.get(QueueEntryStatus.CALLED, 0),
                "in_progress": status_counts.get(
                    QueueEntryStatus.IN_PROGRESS, 0
                ),
                "active_visits": active_visits,
                "patients": total_patients,
                "staff_active": staff_total,
                "staff_on_duty": staff_on_duty,
                "appointments_today": appointments_today,
            },
            "critical_waiting": critical_waiting,
            "departments": list(departments.values()),
            "on_duty_staff": on_duty_staff,
        }

    # ---------------------------------------------------------
    # DEPARTMENT DEEP-DIVE (single department snapshot)
    # ---------------------------------------------------------

    async def get_department_overview(self, dept_id: UUID) -> dict:
        """
        Live snapshot for one department — a convenience wrapper used by the
        dashboard drill-down. Reuses the same aggregation logic as the
        hospital-wide overview, filtered to a single department.
        """
        overview = await self.get_overview()

        dept = next(
            (d for d in overview["departments"] if d["dept_id"] == dept_id),
            None,
        )

        if dept is None:
            # Department exists but has no queue activity yet
            department = await self.db.get(Department, dept_id)
            if department is None:
                return None
            dept = {
                "dept_id": department.dept_id,
                "name": department.name,
                "code": department.department_code,
                "type": department.type.value,
                "is_active": department.is_active,
                "max_capacity": department.max_capacity,
                "waiting": 0,
                "called": 0,
                "in_progress": 0,
                "critical_waiting": 0,
                "staff_on_duty": 0,
            }

        return dept

    # ---------------------------------------------------------
    # AUDIT LOG ACCESS (read side of the audit ledger)
    # ---------------------------------------------------------

    async def get_audit_logs(
        self,
        staff_id: UUID | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """
        Filtered audit-trail listing for the admin audit panel.
        Complements AuditService.get_entity_history (per-entity timelines).
        """
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())

        if staff_id is not None:
            stmt = stmt.where(AuditLog.performed_by == staff_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action.strip().upper())
        if entity_type is not None:
            stmt = stmt.where(
                AuditLog.entity_type == entity_type.strip().upper()
            )
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)

        stmt = stmt.limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ---------------------------------------------------------
    # STAFF ROSTER (full, for the admin staff panel)
    # ---------------------------------------------------------

    async def get_staff_roster(
        self,
        include_inactive: bool = True,
    ) -> list[Staff]:
        """
        Complete staff listing with department and duty info for the
        admin staff-management panel. Unlike StaffService.get_all_staff,
        inactive members are included by default (admins manage them).
        """
        stmt = (
            select(Staff)
            .options(selectinload(Staff.department))
            .order_by(Staff.last_name, Staff.first_name)
        )
        if not include_inactive:
            stmt = stmt.where(Staff.is_active == True)  # noqa: E712

        result = await self.db.execute(stmt)
        return list(result.scalars().all())
