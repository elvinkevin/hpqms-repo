"""
websocket_manager.py

Manages all active WebSocket connections.

Two types of client connect:
  1. Staff dashboards  — connect to /ws/staff/{staff_id}
                         Receive STAFF_ALERT events addressed to their staff_id.

  2. Display boards    — connect to /ws/display/{dept_id}
                         Receive QUEUE_UPDATE events for their department.
                         On each QUEUE_UPDATE they call GET /queues/{dept_id}/tokens
                         to refresh (no queue data embedded in the event).

The manager registers itself with DashboardChannel and DisplayBoardChannel
on startup so those channels can push events to connected clients.
"""

import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import WebSocket

from app.infrastructure.notifications.channels import (
    subscribe_dashboard, unsubscribe_dashboard,
)

logger = logging.getLogger(__name__)


class WebSocketManager:

    def __init__(self):
        # staff_id (str) → WebSocket
        self._staff_connections:   dict[str, WebSocket] = {}
        # dept_id  (str) → list of WebSocket (multiple boards per dept)
        self._display_connections: dict[str, list[WebSocket]] = {}

        # Register with the channel event bus
        subscribe_dashboard(self._on_channel_event)

    # ── Staff dashboard connections ───────────────────────────────────────

    async def connect_staff(self, staff_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._staff_connections[staff_id] = ws
        logger.info("Staff WS connected: %s  (total: %d)", staff_id, len(self._staff_connections))

    def disconnect_staff(self, staff_id: str) -> None:
        self._staff_connections.pop(staff_id, None)
        logger.info("Staff WS disconnected: %s", staff_id)

    async def send_to_staff(self, staff_id: str, payload: dict) -> bool:
        ws = self._staff_connections.get(staff_id)
        if not ws:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception as exc:
            logger.warning("Failed to send to staff %s: %s", staff_id, exc)
            self.disconnect_staff(staff_id)
            return False

    # ── Display board connections ─────────────────────────────────────────

    async def connect_display(self, dept_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._display_connections.setdefault(dept_id, []).append(ws)
        logger.info("Display WS connected for dept %s  (boards: %d)",
                    dept_id, len(self._display_connections[dept_id]))

    def disconnect_display(self, dept_id: str, ws: WebSocket) -> None:
        connections = self._display_connections.get(dept_id, [])
        if ws in connections:
            connections.remove(ws)

    async def broadcast_to_display(self, dept_id: str, payload: dict) -> int:
        """Broadcast to all display boards for a department. Returns delivery count."""
        connections = list(self._display_connections.get(dept_id, []))
        delivered = 0
        dead = []
        for ws in connections:
            try:
                await ws.send_json(payload)
                delivered += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_display(dept_id, ws)
        return delivered

    # ── Channel event bus handler ─────────────────────────────────────────

    async def _on_channel_event(self, event: dict) -> None:
        """Called by DashboardChannel and DisplayBoardChannel when they fire."""
        event_type = event.get("type")

        if event_type == "STAFF_ALERT":
            staff_id = event.get("staff_id", "")
            await self.send_to_staff(staff_id, event)

        elif event_type == "QUEUE_UPDATE":
            dept_id = event.get("dept_id", "")
            await self.broadcast_to_display(dept_id, event)


# Module-level singleton
ws_manager = WebSocketManager()
