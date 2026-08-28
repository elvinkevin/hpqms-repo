import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.routes.websocket_manager import ws_manager
from app.db.session import get_db
from app.main import app


@pytest.fixture(autouse=True)
def reset_display_connections():
    ws_manager._display_connections.clear()
    ws_manager._staff_connections.clear()
    yield
    ws_manager._display_connections.clear()
    ws_manager._staff_connections.clear()


@pytest.mark.asyncio
async def test_display_snapshot_endpoint_returns_authoritative_snapshot(client):
    response = await client.get("/api/display/snapshot")

    assert response.status_code == 200

    body = response.json()
    assert body["facility_name"] == "HPQMS Healthcare"
    assert "server_timestamp" in body
    assert isinstance(body["departments"], list)
    assert isinstance(body["announcements"], list)


def test_display_websocket_endpoint_accepts_connections():
    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/display"):
            pass


def test_display_websocket_sends_connection_established_event():
    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/display") as websocket:
            payload = websocket.receive_json()

            assert payload["event_type"] == "CONNECTION_ESTABLISHED"
            assert payload["message"] == (
                "Connected to the HPQMS public display stream"
            )


def test_display_websocket_connection_is_registered_in_ws_manager():
    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/display"):
            assert "__all__" in ws_manager._display_connections
            assert len(ws_manager._display_connections["__all__"]) == 1


def test_display_broadcast_reaches_connected_display():
    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/display") as websocket:
            payload = websocket.receive_json()
            assert payload["event_type"] == "CONNECTION_ESTABLISHED"

            asyncio.run(
                ws_manager.broadcast_queue_updated(
                    dept_id=None,
                    message="Queue updated",
                    department_name="Global",
                )
            )

            broadcast_payload = websocket.receive_json()
            assert broadcast_payload["event_type"] == "QUEUE_UPDATED"
            assert broadcast_payload["message"] == "Queue updated"


def test_display_disconnect_removes_connection():
    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/display"):
            assert ws_manager._display_connections["__all__"]

    assert "__all__" not in ws_manager._display_connections
