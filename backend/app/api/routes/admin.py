from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domain.schemas.schemas import AuditLogRead
from app.domain.services.admin_service import AdminService
from app.domain.services.auth_service import get_current_user, require_role
from app.domain.models.models import StaffRole

router = APIRouter(
    prefix="/admin",
    tags=["Admin Dashboard"],
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)


# ============================================================================
# LIVE HOSPITAL OVERVIEW
# ============================================================================


@router.get("/overview")
async def get_hospital_overview(
    service: AdminService = Depends(AdminService.get_instance),
):
    """
    Single hospital-wide snapshot for the admin dashboard landing page.

    Returns live totals (queue states, active visits, staff on duty,
    appointments today), a per-department queue breakdown, and the
    current on-duty roster. Read-only.
    """
    return await service.get_overview()


@router.get("/departments/{dept_id}/overview")
async def get_department_overview(
    dept_id: UUID,
    service: AdminService = Depends(AdminService.get_instance),
):
    """
    Live queue/staff snapshot for a single department (dashboard drill-down).
    """
    overview = await service.get_department_overview(dept_id)

    if overview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found.",
        )

    return overview


# ============================================================================
# AUDIT TRAIL
# ============================================================================


@router.get(
    "/audit-logs",
    response_model=list[AuditLogRead],
)
async def list_audit_logs(
    staff_id: UUID | None = Query(default=None),
    action: str | None = Query(
        default=None,
        description="Exact action code, e.g. ROLE_CHANGED, PASSWORD_RESET",
    ),
    entity_type: str | None = Query(default=None),
    entity_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AdminService = Depends(AdminService.get_instance),
):
    """
    Filtered audit-trail listing (newest first). Admin-only.
    """
    return await service.get_audit_logs(
        staff_id=staff_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
