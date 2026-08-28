from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import Department
from app.domain.schemas.schemas import (
    DepartmentCreate,
    DepartmentUpdate,
)


class DepartmentService:
    """
    Handles CRUD operations for hospital departments.
    This service does NOT contain any queue or routing logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    async def create_department(
        self,
        data: DepartmentCreate,
    ) -> Department:
        """
        Creates a new department.
        """
        code = data.department_code.strip().upper()

        existing = await self.db.execute(
            select(Department).where(Department.department_code == code)
        )

        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Department code already exists.",
            )

        payload = data.model_dump()
        payload["department_code"] = code
        payload["name"] = payload["name"].strip()

        department = Department(**payload)
        self.db.add(department)

        try:
            await self.db.flush()
            await self.db.refresh(department)
            return department

        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Department already exists.",
        )
    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------

    async def get_by_id(
        self,
        dept_id: UUID,
    ) -> Department:

        department = await self.db.get(
            Department,
            dept_id,
        )

        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found.",
            )

        return department

    async def get_by_code(
        self,
        department_code: str,
    ) -> Department:

        result = await self.db.execute(
            select(Department).where(
                Department.department_code == department_code.upper()
            )
        )

        department = result.scalar_one_or_none()

        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Department '{department_code}' not found.",
            )

        return department

    async def get_active_departments(
        self,
    ) -> list[Department]:

        result = await self.db.execute(
            select(Department)
            .where(Department.is_active.is_(True))
            .order_by(Department.name)
        )

        return list(result.scalars().all())

    async def get_all(
        self,
    ) -> list[Department]:

        result = await self.db.execute(
            select(Department)
            .order_by(Department.name)
        )

        return list(result.scalars().all())

    async def department_exists(
        self,
        dept_id: UUID,
    ) -> bool:

        result = await self.db.execute(
            select(Department.dept_id).where(
                Department.dept_id == dept_id
            )
        )

        return result.scalar_one_or_none() is not None

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    async def update_department(
        self,
        dept_id: UUID,
        data: DepartmentUpdate,
    ) -> Department:

        department = await self.get_by_id(dept_id)

        updates = data.model_dump(exclude_unset=True)

        if "department_code" in updates:
            updates["department_code"] = updates["department_code"].upper()

        for field, value in updates.items():
            setattr(department, field, value)

        try:
            await self.db.flush()
            await self.db.refresh(department)
            return department

        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Department code already exists.",
            )

    # ---------------------------------------------------------
    # SOFT DELETE
    # ---------------------------------------------------------

    async def deactivate_department(
        self,
        dept_id: UUID,
    ) -> Department:

        department = await self.get_by_id(dept_id)

        department.is_active = False

        await self.db.flush()
        await self.db.refresh(department)

        return department

    async def activate_department(
        self,
        dept_id: UUID,
    ) -> Department:

        department = await self.get_by_id(dept_id)

        department.is_active = True

        await self.db.flush()
        await self.db.refresh(department)

        return department