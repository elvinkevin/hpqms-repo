from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.models import ServicePoint, Staff, QueueEntry, QueueEntryStatus
from app.domain.schemas.schemas import (
    ServicePointCreate,
    ServicePointUpdate,
)

class ServicePointService:

    @staticmethod
    async def create_service_point(db: AsyncSession, data: ServicePointCreate) -> ServicePoint:
        # Check if code is already unique within the department
        existing = await db.scalar(
            select(ServicePoint).where(
                ServicePoint.dept_id == data.dept_id,
                ServicePoint.code == data.code
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service point with code '{data.code}' already exists in this department."
            )

        service_point = ServicePoint(**data.model_dump())
        db.add(service_point)
        await db.commit()
        await db.refresh(service_point)
        return service_point

    @staticmethod
    async def get_service_point(db: AsyncSession, service_point_id: UUID) -> ServicePoint:
        sp = await db.get(ServicePoint, service_point_id)
        if not sp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service point not found."
            )
        return sp

    @staticmethod
    async def list_service_points(db: AsyncSession, dept_id: UUID) -> List[ServicePoint]:
        stmt = select(ServicePoint).where(ServicePoint.dept_id == dept_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_service_point(
        db: AsyncSession, service_point_id: UUID, data: ServicePointUpdate
    ) -> ServicePoint:
        sp = await ServicePointService.get_service_point(db, service_point_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(sp, key, value)

        # Deactivating a station releases any staff checked into it.
        if update_data.get("is_active") is False:
            await ServicePointService.check_out_staff_of_service_point(
                db, sp.service_point_id
            )

        await db.commit()
        await db.refresh(sp)
        return sp

    @staticmethod
    async def check_in_staff(
        db: AsyncSession, staff: Staff, service_point_id: UUID
    ) -> Staff:
        sp = await ServicePointService.get_service_point(db, service_point_id)

        # A decommissioned/inactive station cannot be occupied.
        if not sp.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service point is not active."
            )

        # Enforce same department check
        if sp.dept_id != staff.dept_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Staff member cannot check into a service point outside their department."
            )

        # Only one active staff member may occupy a station at a time
        existing_occupant = await db.scalar(
            select(Staff).where(
                Staff.active_service_point_id == service_point_id,
                Staff.staff_id != staff.staff_id,
                Staff.is_active == True
            )
        )
        if existing_occupant:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Service point is already occupied by staff {existing_occupant.first_name} {existing_occupant.last_name}."
            )

        staff.active_service_point_id = service_point_id
        await db.commit()
        await db.refresh(staff)
        return staff

    @staticmethod
    async def check_out_staff(db: AsyncSession, staff: Staff) -> Staff:
        staff.active_service_point_id = None
        await db.commit()
        await db.refresh(staff)
        return staff

    @staticmethod
    async def check_out_staff_of_service_point(
        db: AsyncSession, service_point_id: UUID
    ) -> Optional[Staff]:
        """Release a service point when it is deactivated or deleted."""
        result = await db.execute(
            select(Staff).where(Staff.active_service_point_id == service_point_id)
        )
        staff_members = list(result.scalars().all())

        for member in staff_members:
            member.active_service_point_id = None

        if staff_members:
            await db.commit()

        return staff_members[0] if staff_members else None

    @staticmethod
    async def get_department_occupancy(db: AsyncSession, dept_id: UUID) -> List[dict]:
        """Returns a snapshot of service points, who is checked in, and current active patient."""
        service_points = await ServicePointService.list_service_points(db, dept_id)
        occupancy_board = []

        for sp in service_points:
            # Find staff currently checked in here
            current_staff = await db.scalar(
                select(Staff).where(Staff.active_service_point_id == sp.service_point_id)
            )

            # Find active queue entry currently at this service point
            active_entry_result = await db.execute(
                select(QueueEntry)
                .options(selectinload(QueueEntry.visit))
                .where(
                    QueueEntry.service_point_id == sp.service_point_id,
                    QueueEntry.status.in_([QueueEntryStatus.CALLED, QueueEntryStatus.IN_PROGRESS])
                )
            )
            active_entry = active_entry_result.scalar_one_or_none()

            occupancy_board.append({
                "service_point": sp,
                "current_staff": current_staff,
                "active_entry": active_entry
            })

        return occupancy_board