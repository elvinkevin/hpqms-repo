from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.domain.models.models import Staff, StaffRole
from app.domain.schemas.schemas import AuditLogRead
from app.domain.services.admin_service import AdminService
from app.domain.services.auth_service import get_current_user, require_role
from app.api.routes.websocket_manager import ws_manager

router = APIRouter(
    prefix="/admin",
    tags=["Admin Dashboard"],
    dependencies=[Depends(require_role(StaffRole.ADMIN))],
)

websocket_router = APIRouter(tags=["Admin Dashboard"])


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


# ============================================================================
# LIVE UPDATE WEBSOCKET
# ============================================================================


@websocket_router.websocket("/ws/admin")
async def admin_websocket_endpoint(
    websocket: WebSocket,
    token: str | None = None,
):
    """
    Live-update channel for the admin dashboard.

    Auth is done via the `token` query parameter (browsers cannot set
    Authorization headers on WebSocket handshakes). Only active ADMIN
    accounts are admitted; anything else is rejected during the handshake.

    The channel carries lightweight `ADMIN_OVERVIEW_CHANGED` pings whenever a
    queue/display event occurs anywhere in the hospital; clients refresh
    their snapshot through the overview API in response.
    """

    def _reject(code: int, reason: str):
        return websocket.close(code=code, reason=reason)

    if not token:
        await _reject(4401, "Missing token.")
        return

    try:
        payload = decode_access_token(token)
    except HTTPException:
        await _reject(4401, "Invalid or expired token.")
        return

    staff_id = payload.get("sub")

    if not staff_id:
        await _reject(4401, "Invalid token payload.")
        return

    async with AsyncSessionLocal() as db:
        staff = await db.get(Staff, UUID(staff_id))

    if (
        staff is None
        or not staff.is_active
        or staff.role != StaffRole.ADMIN
        or not staff.admin_setup_complete
        or staff.requires_password_change
    ):
        await _reject(4403, "Active, fully set up admin role required.")
        return

    await ws_manager.connect_admin(websocket)

    try:
        while True:
            # Client pings keep the connection alive; payloads are ignored.
            await websocket.receive_text()

    except WebSocketDisconnect:
        ws_manager.disconnect_admin(websocket)
