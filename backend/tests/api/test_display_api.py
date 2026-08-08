import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.asyncio
async def test_display_snapshot_endpoint_returns_expected_shape(client):
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
