import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage public display websocket connections and broadcast display events."""

    def __init__(self) -> None:
        self._display_connections: dict[str, list[WebSocket]] = {}
        self._staff_connections: dict[str, WebSocket] = {}

    async def connect_display(
        self,
        dept_id: Optional[str],
        websocket: WebSocket,
    ) -> None:
        await websocket.accept()
        key = dept_id or "__all__"
        self._display_connections.setdefault(key, []).append(websocket)
        logger.info(
            "Display websocket connected for department %s (total=%d)",
            dept_id or "all",
            len(self._display_connections[key]),
        )

        await websocket.send_json(
            {
                "event_id": str(uuid4()),
                "event_type": "CONNECTION_ESTABLISHED",
                "priority": "NORMAL",
                "dept_id": dept_id,
                "department_name": None,
                "message": "Connected to the HPQMS public display stream",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def disconnect_display(
        self,
        dept_id: Optional[str],
        websocket: WebSocket,
    ) -> None:
        key = dept_id or "__all__"
        connections = self._display_connections.get(key, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._display_connections.pop(key, None)

    async def broadcast_display(
        self,
        payload: dict[str, Any],
        dept_id: Optional[str] = None,
    ) -> int:
        """
        Broadcast a display event.

        If dept_id is provided:
            - Send to displays subscribed to that department.
            - Send to global displays.

        If dept_id is None:
            - Send to every connected display.
        """

        if dept_id is not None:
            keys = [
                dept_id,
                "__all__",
            ]
        else:
            keys = list(self._display_connections.keys())

        delivered = 0
        dead_connections: list[tuple[str, WebSocket]] = []

        for key in dict.fromkeys(keys):
            connections = list(
                self._display_connections.get(key, [])
            )

            for websocket in connections:
                try:
                    await websocket.send_json(payload)
                    delivered += 1

                except Exception:
                    dead_connections.append(
                        (key, websocket)
                    )

        for key, websocket in dead_connections:
            connections = self._display_connections.get(key, [])

            if websocket in connections:
                connections.remove(websocket)

            if not connections:
                self._display_connections.pop(key, None)

        return delivered

    async def connect_staff(self, staff_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._staff_connections[staff_id] = websocket

    def disconnect_staff(self, staff_id: str) -> None:
        self._staff_connections.pop(staff_id, None)

    async def send_to_staff(self, staff_id: str, payload: dict[str, Any]) -> bool:
        websocket = self._staff_connections.get(staff_id)
        if websocket is None:
            return False

        try:
            await websocket.send_json(payload)
            return True
        except Exception:
            self.disconnect_staff(staff_id)
            return False

    async def broadcast_token_called(
        self,
        dept_id: str,
        token_number: str,
        service_point: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        department_name: Optional[str] = None,
        message: Optional[str] = None,
        priority: str = "HIGH",
    ) -> int:
        payload = {
            "event_id": str(uuid4()),
            "event_type": "TOKEN_CALLED",
            "priority": priority,
            "dept_id": dept_id,
            "department_name": department_name,
            "token_number": token_number,
            "service_point": service_point,
            "message": message or f"Token {token_number} called to {service_point or 'service point'}",
            "occurred_at": (
                occurred_at.isoformat() if occurred_at else datetime.now(timezone.utc).isoformat()
            ),
        }
        return await self.broadcast_display(payload, dept_id=dept_id)

    async def broadcast_queue_updated(
        self,
        dept_id: Optional[str] = None,
        message: Optional[str] = None,
        department_name: Optional[str] = None,
        priority: str = "NORMAL",
    ) -> int:
        payload = {
            "event_id": str(uuid4()),
            "event_type": "QUEUE_UPDATED",
            "priority": priority,
            "dept_id": dept_id,
            "department_name": department_name,
            "message": message,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        return await self.broadcast_display(payload, dept_id=dept_id)

    async def broadcast_token_completed(
        self,
        dept_id: str,
        token_number: str,
        occurred_at: Optional[datetime] = None,
        department_name: Optional[str] = None,
        message: Optional[str] = None,
        priority: str = "NORMAL",
    ) -> int:
        payload = {
            "event_id": str(uuid4()),
            "event_type": "TOKEN_COMPLETED",
            "priority": priority,
            "dept_id": dept_id,
            "department_name": department_name,
            "token_number": token_number,
            "message": message or f"Token {token_number} completed",
            "occurred_at": (
                occurred_at.isoformat() if occurred_at else datetime.now(timezone.utc).isoformat()
            ),
        }
        return await self.broadcast_display(payload, dept_id=dept_id)

    async def broadcast_token_cancelled(
        self,
        dept_id: str,
        token_number: str,
        occurred_at: Optional[datetime] = None,
        department_name: Optional[str] = None,
        message: Optional[str] = None,
        priority: str = "NORMAL",
    ) -> int:
        payload = {
            "event_id": str(uuid4()),
            "event_type": "TOKEN_CANCELLED",
            "priority": priority,
            "dept_id": dept_id,
            "department_name": department_name,
            "token_number": token_number,
            "message": message or f"Token {token_number} cancelled",
            "occurred_at": (
                occurred_at.isoformat() if occurred_at else datetime.now(timezone.utc).isoformat()
            ),
        }
        return await self.broadcast_display(payload, dept_id=dept_id)

    async def broadcast_announcement_created(
        self,
        announcement_id: str,
        message: str,
        priority: str = "INFO",
        starts_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> int:
        payload = {
            "event_id": str(uuid4()),
            "event_type": "ANNOUNCEMENT_CREATED",
            "priority": priority,
            "announcement_id": announcement_id,
            "announcement_priority": priority,
            "message": message,
            "starts_at": starts_at.isoformat() if starts_at else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        return await self.broadcast_display(payload)


    async def broadcast_department(
        self,
        payload: dict[str, Any],
        dept_id: Optional[str] = None,
    ) -> int:
        """
        Broadcast an event to staff connections or display fallback connections
        belonging to a given department.
        """
        delivered = 0
        dead_staff: list[str] = []

        # Send to active staff connections
        for staff_id, websocket in list(self._staff_connections.items()):
            try:
                await websocket.send_json(payload)
                delivered += 1
            except Exception:
                dead_staff.append(staff_id)

        for staff_id in dead_staff:
            self.disconnect_staff(staff_id)

        # Also forward to display channels for public/department tracking
        display_delivered = await self.broadcast_display(
            payload,
            dept_id=dept_id,
        )

        return delivered + display_delivered


ws_manager = WebSocketManager()
