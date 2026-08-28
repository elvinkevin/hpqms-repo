from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.models import Staff, StaffRole
from app.domain.schemas.schemas import (
    StaffCreate,
    StaffDutyStatusRead,
    StaffRead,
    StaffUpdate,
)
from app.core.security import hash_password
from sqlalchemy.orm import selectinload

class StaffService:
    """
    Service responsible for staff management.

    Responsibilities:
        • Register staff
        • Retrieve staff
        • Update staff
        • Manage duty status
        • Activate / deactivate staff

    Authentication is handled separately by AuthService.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @classmethod
    def get_instance(
        cls,
        db: AsyncSession = Depends(get_db),
    ):
        """
        Dynamically provides an instance of StaffService to FastAPI routes.
        """
        return cls(db)

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create_staff(
        self,
        data: StaffCreate,
    ) -> Staff:

        existing = await self.get_by_employee_id(
            data.employee_id
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Employee ID already exists.",
            )

        staff = Staff(
            employee_id=data.employee_id,
            first_name=data.first_name,
            last_name=data.last_name,
            dept_id=data.dept_id,
            role=data.role,
            specialization=data.specialization,
            hashed_password=hash_password(data.password),
        )

        self.db.add(staff)

        try:
            await self.db.flush()
            await self.db.refresh(staff)
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unable to create staff member.",
            )

        return staff

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    async def get_by_id(
        self,
        staff_id: UUID,
    ) -> Staff:

        staff = await self.db.get(
            Staff,
            staff_id,
        )

        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found.",
            )

        return staff

    async def get_staff(self, staff_id: UUID) -> Staff:
        """
        Retrieve a staff member by UUID.
        """
        return await self.get_by_id(staff_id)

    async def get_by_employee_id(
        self,
        employee_id: str,
    ) -> Staff | None:

        result = await self.db.execute(
            select(Staff).where(
                Staff.employee_id == employee_id
            )
        )

        return result.scalar_one_or_none()

    async def get_all_staff(self) -> list[Staff]:
        """
        Returns all staff ordered alphabetically.
        """

        result = await self.db.execute(
            select(Staff)
            .options(selectinload(Staff.department))
            .order_by(
                Staff.last_name,
                Staff.first_name,
            )
        )

        return list(result.scalars().all())

    async def get_by_department(
        self,
        dept_id: UUID,
    ) -> list[Staff]:

        result = await self.db.execute(
            select(Staff)
            .where(
                Staff.dept_id == dept_id,
                Staff.is_active == True,
            )
            .order_by(
                Staff.last_name,
                Staff.first_name,
            )
        )

        return list(result.scalars().all())

    async def get_by_role(
        self,
        role: StaffRole,
    ) -> list[Staff]:

        result = await self.db.execute(
            select(Staff)
            .where(
                Staff.role == role,
                Staff.is_active == True,
            )
            .order_by(
                Staff.last_name,
                Staff.first_name,
            )
        )

        return list(result.scalars().all())

    async def search_staff(
        self,
        search_term: str,
    ) -> list[Staff]:

        result = await self.db.execute(
            select(Staff).where(
                or_(
                    Staff.first_name.ilike(f"%{search_term}%"),
                    Staff.last_name.ilike(f"%{search_term}%"),
                    Staff.employee_id.ilike(f"%{search_term}%"),
                )
            )
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update_staff(
        self,
        staff_id: UUID,
        data: StaffUpdate,
    ) -> Staff:

        staff = await self.get_by_id(staff_id)

        updates = data.model_dump(
            exclude_unset=True
        )

        for field, value in updates.items():
            setattr(staff, field, value)

        try:
            await self.db.flush()
            await self.db.refresh(staff)
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unable to update staff record.",
            )

        return staff

    # ---------------------------------------------------------
    # DUTY MANAGEMENT
    # ---------------------------------------------------------

    async def set_on_duty(
        self,
        staff_id: UUID,
    ) -> Staff:

        staff = await self.get_by_id(staff_id)

        staff.is_on_duty = True

        await self.db.flush()

        return staff

    async def set_off_duty(
        self,
        staff_id: UUID,
    ) -> Staff:

        staff = await self.get_by_id(staff_id)

        staff.is_on_duty = False

        await self.db.flush()

        return staff

    # ---------------------------------------------------------
    # ACCOUNT STATUS
    # ---------------------------------------------------------

    async def activate_staff(
        self,
        staff_id: UUID,
    ) -> Staff:

        staff = await self.get_by_id(staff_id)

        staff.is_active = True

        await self.db.flush()

        return staff

    async def deactivate_staff(
        self,
        staff_id: UUID,
    ) -> Staff:

        staff = await self.get_by_id(staff_id)

        staff.is_active = False
        staff.is_on_duty = False

        await self.db.flush()

        return staff

    
    async def get_me(self, staff_id: UUID) -> Staff:
            return await self.get_staff(staff_id)


    async def check_in(self, staff_id: UUID) -> Staff:
        staff = await self.get_staff(staff_id)

        if not staff.is_active:
            raise HTTPException(
                status_code=403,
                detail="Inactive staff account."
            )

        if staff.is_on_duty:
            raise HTTPException(
                status_code=409,
                detail="Staff member is already checked in."
            )

        staff.is_on_duty = True

        await self.db.flush()
        await self.db.refresh(staff)

        return staff


    async def check_out(self, staff_id: UUID) -> Staff:
        staff = await self.get_staff(staff_id)

        if not staff.is_on_duty:
            raise HTTPException(
                status_code=409,
                detail="Staff member is already checked out."
            )

        staff.is_on_duty = False

        await self.db.flush()
        await self.db.refresh(staff)

        return staff


    

    async def get_my_status(
        self,
        staff_id: UUID,
    ) -> StaffDutyStatusRead:

        staff = await self.get_staff(staff_id)

        return StaffDutyStatusRead(
            staff_id=staff.staff_id,
            employee_id=staff.employee_id,
            full_name=f"{staff.first_name} {staff.last_name}",
            role=staff.role,
            dept_id=staff.dept_id,
            is_on_duty=staff.is_on_duty,
        )




    async def get_active_staff(self) -> list[Staff]:
        """
        Returns all active staff ordered alphabetically.
        """

        result = await self.db.execute(
            select(Staff)
            .options(selectinload(Staff.department))
            .where(Staff.is_active == True)
            .order_by(
                Staff.last_name,
                Staff.first_name,
            )
        )

        return list(result.scalars().all())
# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------

    async def staff_exists(
        self,
        staff_id: UUID,
    ) -> bool:
        """
        Returns True if the staff member exists.
        """

        return await self.db.get(Staff, staff_id) is not None
    # async def get_department_staff(
    #     dept_id: UUID,
    # ) -> list[Staff]
    TODO:...
    #     async def get_available_department_staff(
    #     dept_id: UUID,
    # ) -> list[Staff]
    TODO:...