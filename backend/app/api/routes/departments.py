from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.models import StaffRole
from app.domain.schemas.schemas import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentRead,
)
from app.domain.services.auth_service import (
    get_current_user,
    require_role,
)
from app.domain.services.departments_service import DepartmentService


router = APIRouter(
    prefix="/departments",
    tags=["Department Management"],
)


# ---------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------

@router.post(
    "",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(StaffRole.ADMIN))]
)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new hospital department.
    """
    service = DepartmentService(db)

    department = await service.create_department(data)

    await db.commit()

    return department


# ---------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------

@router.get(
    "",
    response_model=list[DepartmentRead],
    dependencies=[Depends(get_current_user)]
)
async def get_departments(
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all hospital departments.
    """
    service = DepartmentService(db)

    return await service.get_all()


@router.get(
    "/active",
    response_model=list[DepartmentRead],
    dependencies=[Depends(get_current_user)]
)
async def get_active_departments(
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all active departments.
    """
    service = DepartmentService(db)

    return await service.get_active_departments()


@router.get(
    "/{department_id}",
    response_model=DepartmentRead,
    dependencies=[Depends(get_current_user)]
)
async def get_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a department by UUID.
    """
    service = DepartmentService(db)

    return await service.get_by_id(department_id)


# ---------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------

@router.patch(
    "/{department_id}",
    response_model=DepartmentRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))]
)
async def update_department(
    department_id: UUID,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update department details.
    """
    service = DepartmentService(db)

    department = await service.update_department(
        department_id,
        data,
    )

    await db.commit()

    return department


# ---------------------------------------------------------------------
# ACTIVATE
# ---------------------------------------------------------------------

@router.patch(
    "/{department_id}/activate",
    response_model=DepartmentRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))]
)
async def activate_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Activate a department.
    """
    service = DepartmentService(db)

    department = await service.activate_department(
        department_id
    )

    await db.commit()

    return department


# ---------------------------------------------------------------------
# DEACTIVATE
# ---------------------------------------------------------------------

@router.patch(
    "/{department_id}/deactivate",
    response_model=DepartmentRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))]
)
async def deactivate_department(
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate a department.
    """
    service = DepartmentService(db)

    department = await service.deactivate_department(
        department_id
    )

    await db.commit()

    return department