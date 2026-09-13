from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.models import Staff, StaffRole
from app.domain.schemas.schemas import (
    CurrentUser,
    ServicePointCreate,
    ServicePointOccupancy,
    ServicePointRead,
    ServicePointUpdate,
    StaffCheckInRequest,
    StaffRead,
)
from app.domain.services.auth_service import (
    ensure_department_access,
    get_current_user,
    require_role,
)
from app.domain.services.service_points_service import ServicePointService

router = APIRouter(
    tags=["Service Points & Stations"],
)


@router.post(
    "/departments/{dept_id}/service-points",
    response_model=ServicePointRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_role(
                StaffRole.ADMIN,
            )
        )
    ],
)
async def create_service_point(
    dept_id: UUID,
    payload: ServicePointCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new service point (desk, room, window) within a department."""
    ensure_department_access(current_user, dept_id)
    # Ensure path matches payload dept_id
    payload.dept_id = dept_id
    return await ServicePointService.create_service_point(db, payload)


@router.get(
    "/departments/{dept_id}/service-points",
    response_model=List[ServicePointRead],
)
async def list_department_service_points(
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all service points configured for a department."""
    ensure_department_access(current_user, dept_id)
    return await ServicePointService.list_service_points(db, dept_id)


@router.patch(
    "/service-points/{service_point_id}",
    response_model=ServicePointRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.ADMIN,
            )
        )
    ],
)
async def update_service_point(
    service_point_id: UUID,
    payload: ServicePointUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update service point details (label, type, active status)."""
    sp = await ServicePointService.get_service_point(db, service_point_id)
    ensure_department_access(current_user, sp.dept_id)
    return await ServicePointService.update_service_point(db, service_point_id, payload)


@router.post(
    "/staff/me/service-point/check-in",
    response_model=StaffRead,
)
async def staff_service_point_check_in(
    payload: StaffCheckInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Check the current staff member into a physical service point/desk.

    Distinct from POST /staff/me/check-in, which toggles duty status.
    """
    # Fetch the actual Staff model instance from the DB using current_user ID
    staff = await db.get(Staff, current_user.staff_id)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff record not found."
        )
    return await ServicePointService.check_in_staff(db, staff, payload.service_point_id)


@router.post(
    "/staff/me/service-point/check-out",
    response_model=StaffRead,
)
async def staff_service_point_check_out(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Check the current staff member out of their current service point."""
    staff = await db.get(Staff, current_user.staff_id)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff record not found."
        )
    return await ServicePointService.check_out_staff(db, staff)


@router.get(
    "/departments/{dept_id}/service-points/status",
    response_model=List[ServicePointOccupancy],
)
async def get_department_occupancy_board(
    dept_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a real-time occupancy board showing desks, assigned staff, and active patients."""
    ensure_department_access(current_user, dept_id)
    board = await ServicePointService.get_department_occupancy(db, dept_id)

    return [
        ServicePointOccupancy(
            service_point=ServicePointRead.model_validate(item["service_point"]),
            current_staff=(
                StaffRead.model_validate(item["current_staff"])
                if item["current_staff"] is not None
                else None
            ),
            active_entry_token=(
                item["active_entry"].visit.token_number
                if item["active_entry"] is not None
                and item["active_entry"].visit is not None
                else None
            ),
            active_entry_id=(
                item["active_entry"].queue_entry_id
                if item["active_entry"] is not None
                else None
            ),
        )
        for item in board
    ]