from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.schemas.schemas import DisplaySnapshot
from app.domain.services.display_service import DisplayService
from app.api.routes.websocket_manager import ws_manager

router = APIRouter(prefix="/display", tags=["Display"])
websocket_router = APIRouter(tags=["Display"])


@router.get("/snapshot", response_model=DisplaySnapshot)
async def get_display_snapshot(
    db: AsyncSession = Depends(get_db),
):
    """Return the authoritative display snapshot for the public display board."""
    service = DisplayService(db)
    return await service.get_snapshot()


from uuid import UUID

@websocket_router.websocket("/ws/display")
async def display_websocket_endpoint(
    websocket: WebSocket,
    department_id: UUID | None = None,
):
    """Accept public display connections and subscribe them to department/global events."""

    department_key = str(department_id) if department_id else None

    await ws_manager.connect_display(
        department_key,
        websocket,
    )

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        ws_manager.disconnect_display(
            department_key,
            websocket,
        )