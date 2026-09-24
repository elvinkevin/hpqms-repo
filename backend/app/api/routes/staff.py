from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.models import StaffRole
from app.domain.schemas.schemas import (
    AdminPasswordResetResponse,
    CurrentUser,
    StaffCreate,
    StaffDepartmentUpdate,
    StaffDutyStatusRead,
    StaffRead,
    StaffRoleUpdate,
    StaffUpdate,
)
from app.domain.services.auth_service import (
    get_current_user,
    require_role,
)
from app.domain.services.staff_service import StaffService
from app.domain.services.audit_service import AuditService

router = APIRouter(
    prefix="/staff",
    tags=["Staff Management"],
)


# ============================================================================
# COLLECTION ROUTES
# ============================================================================


@router.post(
    "/",
    response_model=StaffRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def create_staff_member(
    data: StaffCreate,
    db: AsyncSession = Depends(get_db),
):
    service = StaffService(db)
    staff = await service.create_staff(data)
    await db.commit()
    return staff


@router.get(
    "/",
    response_model=list[StaffRead],
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def list_staff(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    service = StaffService(db)

    if active_only:
        return await service.get_active_staff()

    return await service.get_all_staff()


# ============================================================================
# SELF SERVICE ROUTES (/me) — Declared BEFORE /{staff_id} to prevent 422 errors
# ============================================================================


@router.get(
    "/me",
    response_model=StaffRead,
)
async def get_my_profile(
    current_user: CurrentUser = Depends(get_current_user),
    service: StaffService = Depends(StaffService.get_instance),
):
    return await service.get_me(current_user.staff_id)


@router.post(
    "/me/check-in",
    response_model=StaffRead,
)
async def check_in(
    current_user: CurrentUser = Depends(get_current_user),
    service: StaffService = Depends(StaffService.get_instance),
):
    staff = await service.check_in(current_user.staff_id)
    await service.db.commit()
    return staff


@router.post(
    "/me/check-out",
    response_model=StaffRead,
)
async def check_out(
    current_user: CurrentUser = Depends(get_current_user),
    service: StaffService = Depends(StaffService.get_instance),
):
    staff = await service.check_out(current_user.staff_id)
    await service.db.commit()
    return staff


@router.get(
    "/me/status",
    response_model=StaffDutyStatusRead,
)
async def my_status(
    current_user: CurrentUser = Depends(get_current_user),
    service: StaffService = Depends(StaffService.get_instance),
):
    return await service.get_my_status(current_user.staff_id)


# ============================================================================
# PARAMETERIZED RESOURCE ROUTES ({staff_id})
# ============================================================================


@router.get(
    "/{staff_id}",
    response_model=StaffRead,
    dependencies=[Depends(get_current_user)],
)
async def get_staff(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = StaffService(db)
    return await service.get_staff(staff_id)


@router.put(
    "/{staff_id}",
    response_model=StaffRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def update_staff(
    staff_id: UUID,
    data: StaffUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = StaffService(db)
    staff = await service.update_staff(
        staff_id,
        data,
    )
    await db.commit()
    return staff


@router.patch(
    "/{staff_id}/deactivate",
    response_model=StaffRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def deactivate_staff(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = StaffService(db)
    staff = await service.deactivate_staff(staff_id)
    await db.commit()
    return staff


@router.patch(
    "/{staff_id}/activate",
    response_model=StaffRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def activate_staff(
    staff_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = StaffService(db)
    staff = await service.activate_staff(staff_id)
    await db.commit()
    return staff


@router.patch(
    "/{staff_id}/role",
    response_model=StaffRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def change_staff_role(
    staff_id: UUID,
    data: StaffRoleUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change a staff member's role. Admin-only.
    """
    service = StaffService(db)
    staff = await service.change_role(staff_id, data)

    await AuditService(db).log_action(
        entity_id=staff.staff_id,
        entity_type="STAFF",
        action="ROLE_CHANGED",
        performed_by=current_user.staff_id,
        payload={"new_role": data.role.value},
    )

    await db.commit()
    return staff


@router.patch(
    "/{staff_id}/transfer",
    response_model=StaffRead,
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def transfer_staff_department(
    staff_id: UUID,
    data: StaffDepartmentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Move a staff member to a different department. Admin-only.
    Releases any active service-point binding in the old department.
    """
    service = StaffService(db)
    staff = await service.transfer_department(staff_id, data)

    await AuditService(db).log_action(
        entity_id=staff.staff_id,
        entity_type="STAFF",
        action="DEPARTMENT_TRANSFER",
        performed_by=current_user.staff_id,
        payload={"new_dept_id": str(data.dept_id)},
    )

    await db.commit()
    return staff


@router.patch(
    "/{staff_id}/reset-password",
    response_model=AdminPasswordResetResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)
async def admin_reset_password(
    staff_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Invalidate the current password and issue a one-time recovery code.
    """
    service = StaffService(db)
    _staff, recovery_code = await service.reset_password(staff_id)

    await AuditService(db).log_action(
        entity_id=staff_id,
        entity_type="STAFF",
        action="PASSWORD_RESET",
        performed_by=current_user.staff_id,
    )

    await db.commit()

    return {
        "message": "Password invalidated. Share the recovery code securely.",
        "recovery_code": recovery_code,
        "expires_in_minutes": 15,
    }
