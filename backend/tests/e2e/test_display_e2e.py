import asyncio

import anyio
from fastapi import WebSocketDisconnect
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.api.routes.websocket_manager import ws_manager
from app.domain.models.models import DeptType, Department


@pytest.mark.asyncio
async def test_display_frontend_initial_connection(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Execute snapshot HTTP call
            response = await client.get("/api/display/snapshot")

            assert response.status_code == 200

            snapshot = response.json()

            assert snapshot["facility_name"] == "HPQMS Healthcare"
            assert isinstance(snapshot["departments"], list)
            assert isinstance(snapshot["announcements"], list)
            assert "server_timestamp" in snapshot
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_calling_queue_entry_updates_backend_state(
    db,
    queue_entry,
    receptionist_token_headers,
):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:

            response = await client.patch(
                f"/api/queue/{queue_entry.queue_entry_id}/call",
                headers=receptionist_token_headers,
            )

            assert response.status_code == 200

            body = response.json()

            assert body["queue_entry_id"] == str(
                queue_entry.queue_entry_id
            )
            assert body["status"] == "CALLED"

    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_calling_queue_entry_broadcasts_token_called_to_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end test:

    Queue entry is called
        ↓
    backend updates queue state
        ↓
    WebSocket manager publishes TOKEN_CALLED
        ↓
    connected public display receives the event
    """

    # Commit and flush any active state on the fixture session before passing to FastAPI
    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # 1. Consume WebSocket handshake.
                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # 2. Trigger queue transition.
                response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/call",
                    headers=receptionist_token_headers,
                )

                assert response.status_code == 200

                body = response.json()

                assert body["status"] == "CALLED"
                # Updated: token_number lives on the nested visit object
                assert body["visit"]["token_number"] == "W-101"

                # 3. Verify real-time display event.
                event = websocket.receive_json()

                assert event["event_type"] == "TOKEN_CALLED"
                assert event["token_number"] == "W-101"
                assert event["dept_id"] == str(
                    queue_entry.dept_id
                )

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()

@pytest.mark.asyncio
async def test_starting_called_queue_entry_updates_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end test:

    Queue entry is called
        ↓
    Queue entry is started
        ↓
    Backend state becomes IN_PROGRESS
        ↓
    WebSocket publishes TOKEN_SERVICE_STARTED
        ↓
    Public display receives the event
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # --------------------------------------------------
                # 1. Consume connection handshake
                # --------------------------------------------------

                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # --------------------------------------------------
                # 2. Call the patient
                # --------------------------------------------------

                call_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/call",
                    headers=receptionist_token_headers,
                )

                assert call_response.status_code == 200

                call_body = call_response.json()

                assert call_body["status"] == "CALLED"
                assert call_body["visit"]["token_number"] == "W-101"

                # Consume TOKEN_CALLED event.
                called_event = websocket.receive_json()

                assert called_event["event_type"] == "TOKEN_CALLED"
                assert called_event["token_number"] == "W-101"

                # --------------------------------------------------
                # 3. Start service
                # --------------------------------------------------

                start_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/start",
                    headers=receptionist_token_headers,
                )

                assert start_response.status_code == 200

                start_body = start_response.json()

                assert start_body["status"] == "IN_PROGRESS"
                assert start_body["visit"]["token_number"] == "W-101"

                # --------------------------------------------------
                # 4. Verify display receives TOKEN_SERVICE_STARTED
                # --------------------------------------------------

                update_event = websocket.receive_json()

                assert update_event["event_type"] == (
                    "TOKEN_SERVICE_STARTED"
                )
                assert update_event["token_number"] == "W-101"
                assert update_event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert update_event["status"] == "IN_PROGRESS"

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()


@pytest.mark.asyncio
async def test_completing_in_progress_queue_entry_updates_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end test:

    Queue entry is called
        ↓
    Queue entry is started
        ↓
    Queue entry is completed
        ↓
    Backend state becomes COMPLETED
        ↓
    WebSocket publishes TOKEN_COMPLETED
        ↓
    Public display receives the event
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # --------------------------------------------------
                # 1. Consume connection handshake
                # --------------------------------------------------

                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # --------------------------------------------------
                # 2. Call patient
                # --------------------------------------------------

                call_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/call",
                    headers=receptionist_token_headers,
                )

                assert call_response.status_code == 200
                assert call_response.json()["status"] == "CALLED"

                # Consume TOKEN_CALLED
                called_event = websocket.receive_json()

                assert called_event["event_type"] == "TOKEN_CALLED"
                assert called_event["token_number"] == "W-101"

                # --------------------------------------------------
                # 3. Start service
                # --------------------------------------------------

                start_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/start",
                    headers=receptionist_token_headers,
                )

                assert start_response.status_code == 200
                assert start_response.json()["status"] == "IN_PROGRESS"

                # Consume TOKEN_SERVICE_STARTED
                started_event = websocket.receive_json()

                assert started_event["event_type"] == (
                    "TOKEN_SERVICE_STARTED"
                )
                assert started_event["token_number"] == "W-101"
                assert started_event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert started_event["status"] == "IN_PROGRESS"

                # --------------------------------------------------
                # 4. Complete service
                # --------------------------------------------------

                complete_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/complete",
                    headers=receptionist_token_headers,
                )

                assert complete_response.status_code == 200

                complete_body = complete_response.json()

                assert complete_body["status"] == "COMPLETED"
                assert complete_body["visit"]["token_number"] == "W-101"

                # --------------------------------------------------
                # 5. Verify TOKEN_COMPLETED reaches display
                # --------------------------------------------------

                completed_event = websocket.receive_json()

                assert completed_event["event_type"] == (
                    "TOKEN_COMPLETED"
                )
                assert completed_event["token_number"] == "W-101"
                assert completed_event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert completed_event["status"] == "COMPLETED"

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()


@pytest.mark.asyncio
async def test_cancelling_queue_entry_updates_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end test:

    Queue entry is cancelled
        ↓
    Backend state becomes CANCELLED
        ↓
    WebSocket publishes TOKEN_CANCELLED
        ↓
    Public display receives the event
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # 1. Consume connection handshake.
                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # 2. Cancel the waiting queue entry.
                response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/cancel",
                    headers=receptionist_token_headers,
                )

                assert response.status_code == 200

                body = response.json()

                assert body["status"] == "CANCELLED"
                assert body["visit"]["token_number"] == "W-101"

                # 3. Verify TOKEN_CANCELLED reaches the display.
                event = websocket.receive_json()

                assert event["event_type"] == "TOKEN_CANCELLED"
                assert event["token_number"] == "W-101"
                assert event["dept_id"] == str(
                    queue_entry.dept_id
                )

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()

@pytest.mark.asyncio
async def test_cancelling_queue_entry_broadcasts_token_cancelled_to_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end flow:

    HTTP cancel request
        ↓
    QueueService transitions entry
        ↓
    Database state becomes CANCELLED
        ↓
    WebSocket manager broadcasts TOKEN_CANCELLED
        ↓
    Public display receives the event
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # 1. Consume connection handshake.
                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # 2. Cancel the queue entry through the API.
                response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/cancel",
                    headers=receptionist_token_headers,
                )

                assert response.status_code == 200

                body = response.json()

                # 3. Verify backend state.
                assert body["queue_entry_id"] == str(
                    queue_entry.queue_entry_id
                )

                assert body["status"] == "CANCELLED"

                assert body["visit"]["token_number"] == "W-101"

                # 4. Verify WebSocket event.
                event = websocket.receive_json()

                assert event["event_type"] == "TOKEN_CANCELLED"
                assert event["token_number"] == "W-101"
                assert event["dept_id"] == str(
                    queue_entry.dept_id
                )

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()

@pytest.mark.asyncio
async def test_completing_queue_entry_broadcasts_token_completed_to_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end test:

    Queue entry is called
        ↓
    Queue entry starts service
        ↓
    Queue entry is completed
        ↓
    Backend commits the state
        ↓
    WebSocket manager publishes TOKEN_COMPLETED
        ↓
    Public display receives the event
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # --------------------------------------------------
                # 1. Consume WebSocket handshake
                # --------------------------------------------------

                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # --------------------------------------------------
                # 2. WAITING -> CALLED
                # --------------------------------------------------

                call_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/call",
                    headers=receptionist_token_headers,
                )

                assert call_response.status_code == 200
                assert call_response.json()["status"] == "CALLED"

                # Consume TOKEN_CALLED event.
                called_event = websocket.receive_json()

                assert called_event["event_type"] == "TOKEN_CALLED"
                assert called_event["token_number"] == "W-101"

                # --------------------------------------------------
                # 3. CALLED -> IN_PROGRESS
                # --------------------------------------------------

                start_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/start",
                    headers=receptionist_token_headers,
                )

                assert start_response.status_code == 200
                assert start_response.json()["status"] == "IN_PROGRESS"

                # Consume TOKEN_SERVICE_STARTED event.
                started_event = websocket.receive_json()

                assert started_event["event_type"] == (
                    "TOKEN_SERVICE_STARTED"
                )
                assert started_event["token_number"] == "W-101"
                assert started_event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert started_event["status"] == "IN_PROGRESS"

                # --------------------------------------------------
                # 4. IN_PROGRESS -> COMPLETED
                # --------------------------------------------------

                complete_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/complete",
                    headers=receptionist_token_headers,
                )

                assert complete_response.status_code == 200

                body = complete_response.json()

                assert body["status"] == "COMPLETED"
                assert body["visit"]["token_number"] == "W-101"

                # --------------------------------------------------
                # 5. Verify TOKEN_COMPLETED reached display
                # --------------------------------------------------

                completed_event = websocket.receive_json()

                assert completed_event["event_type"] == (
                    "TOKEN_COMPLETED"
                )
                assert completed_event["token_number"] == "W-101"
                assert completed_event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert completed_event["status"] == "COMPLETED"

    finally:
        app.dependency_overrides.clear()

        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()


@pytest.mark.asyncio
async def test_cancelling_queue_entry_broadcasts_token_cancelled_to_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    WAITING -> CANCELLED
    Backend commits the state and the public display
    receives TOKEN_CANCELLED.
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/cancel",
                    headers=receptionist_token_headers,
                )

                assert response.status_code == 200

                body = response.json()

                assert body["status"] == "CANCELLED"
                assert body["visit"]["token_number"] == "W-101"

                event = websocket.receive_json()

                assert event["event_type"] == "TOKEN_CANCELLED"
                assert event["token_number"] == "W-101"
                assert event["dept_id"] == str(
                    queue_entry.dept_id
                )

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()

@pytest.mark.asyncio
async def test_queue_change_broadcasts_token_service_started_to_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    WAITING -> CALLED -> IN_PROGRESS

    The public display should receive TOKEN_SERVICE_STARTED
    when the patient enters service.
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # --------------------------------------------------
                # 1. Consume WebSocket handshake
                # --------------------------------------------------

                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # --------------------------------------------------
                # 2. WAITING -> CALLED
                # --------------------------------------------------

                call_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/call",
                    headers=receptionist_token_headers,
                )

                assert call_response.status_code == 200
                assert call_response.json()["status"] == "CALLED"

                called_event = websocket.receive_json()

                assert called_event["event_type"] == "TOKEN_CALLED"
                assert called_event["token_number"] == "W-101"

                # --------------------------------------------------
                # 3. CALLED -> IN_PROGRESS
                # --------------------------------------------------

                start_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/start",
                    headers=receptionist_token_headers,
                )

                assert start_response.status_code == 200

                body = start_response.json()

                assert body["status"] == "IN_PROGRESS"
                assert body["visit"]["token_number"] == "W-101"

                # --------------------------------------------------
                # 4. Verify TOKEN_SERVICE_STARTED
                # --------------------------------------------------

                event = websocket.receive_json()

                assert event["event_type"] == (
                    "TOKEN_SERVICE_STARTED"
                )
                assert event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert event["token_number"] == "W-101"
                assert event["status"] == "IN_PROGRESS"

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()


@pytest.mark.asyncio
async def test_event_reaches_only_correct_department_display(
    db,
    async_session_factory,
    queue_entry,
    receptionist_token_headers,
    department,
):
    """
    A queue event for one department must not be delivered
    to another department's display.
    """
    from app.domain.models.models import Department, DeptType

    # 1. Setup second department upfront
    other_department = Department(
        name="Emergency",
        department_code="EMG",
        type=DeptType.OPD,
    )
    db.add(other_department)
    await db.commit()
    await db.refresh(other_department)

    # Convert UUIDs to strings explicitly
    target_dept_str = str(queue_entry.dept_id)
    other_dept_str = str(other_department.dept_id)

    # 2. Bind FastAPI's get_db to a fresh session per request
    async def _override_get_db():
        async with async_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            # Connect target department display
            with test_client.websocket_connect(
                f"/ws/display?dept_id={target_dept_str}"
            ) as department_socket:

                department_handshake = department_socket.receive_json()
                assert department_handshake["event_type"] == "CONNECTION_ESTABLISHED"

                # Connect second department display
                with test_client.websocket_connect(
                    f"/ws/display?dept_id={other_dept_str}"
                ) as other_socket:

                    other_handshake = other_socket.receive_json()
                    assert other_handshake["event_type"] == "CONNECTION_ESTABLISHED"

                    # Trigger event on original department queue
                    response = test_client.patch(
                        f"/api/queue/{queue_entry.queue_entry_id}/call",
                        headers=receptionist_token_headers,
                    )
                    assert response.status_code == 200

                    # 3. Target department receives the event
                    event = department_socket.receive_json()
                    assert event["event_type"] == "TOKEN_CALLED"
                    assert event["token_number"] == "W-101"
                    assert event["dept_id"] == target_dept_str

                    # 4. Verify connection exists under string key in manager
                    other_connections = ws_manager._display_connections.get(
                        other_dept_str,
                        [],
                    )
                    assert other_connections

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()


@pytest.mark.asyncio
async def test_event_reaches_global_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    A queue event generated for a department must also reach
    a global public display connection.
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            # Global display.
            with test_client.websocket_connect(
                "/ws/display"
            ) as global_socket:

                connection_event = global_socket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # Trigger queue event.
                response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/call",
                    headers=receptionist_token_headers,
                )

                assert response.status_code == 200

                body = response.json()

                assert body["status"] == "CALLED"

                # Global display must receive it.
                event = global_socket.receive_json()

                assert event["event_type"] == "TOKEN_CALLED"
                assert event["token_number"] == "W-101"
                assert event["dept_id"] == str(
                    queue_entry.dept_id
                )

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()

@pytest.mark.asyncio
async def test_completing_queue_entry_broadcasts_token_completed_to_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end test:

    Queue entry is called
        ↓
    Queue entry starts service
        ↓
    Queue entry is completed
        ↓
    Backend commits the state
        ↓
    WebSocket manager publishes TOKEN_COMPLETED
        ↓
    Public display receives the event
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # --------------------------------------------------
                # 1. Consume WebSocket handshake
                # --------------------------------------------------

                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # --------------------------------------------------
                # 2. WAITING -> CALLED
                # --------------------------------------------------

                call_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/call",
                    headers=receptionist_token_headers,
                )

                assert call_response.status_code == 200
                assert call_response.json()["status"] == "CALLED"

                # Consume TOKEN_CALLED event.
                called_event = websocket.receive_json()

                assert called_event["event_type"] == "TOKEN_CALLED"
                assert called_event["token_number"] == "W-101"

                # --------------------------------------------------
                # 3. CALLED -> IN_PROGRESS
                # --------------------------------------------------

                start_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/start",
                    headers=receptionist_token_headers,
                )

                assert start_response.status_code == 200
                assert start_response.json()["status"] == "IN_PROGRESS"

                # Consume TOKEN_SERVICE_STARTED event.
                started_event = websocket.receive_json()

                assert started_event["event_type"] == (
                    "TOKEN_SERVICE_STARTED"
                )
                assert started_event["token_number"] == "W-101"
                assert started_event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert started_event["status"] == "IN_PROGRESS"

                # --------------------------------------------------
                # 4. IN_PROGRESS -> COMPLETED
                # --------------------------------------------------

                complete_response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/complete",
                    headers=receptionist_token_headers,
                )

                assert complete_response.status_code == 200

                body = complete_response.json()

                assert body["status"] == "COMPLETED"
                assert body["visit"]["token_number"] == "W-101"

                # --------------------------------------------------
                # 5. Verify TOKEN_COMPLETED reached display
                # --------------------------------------------------

                completed_event = websocket.receive_json()

                assert completed_event["event_type"] == (
                    "TOKEN_COMPLETED"
                )
                assert completed_event["token_number"] == "W-101"
                assert completed_event["dept_id"] == str(
                    queue_entry.dept_id
                )
                assert completed_event["status"] == "COMPLETED"

    finally:
        app.dependency_overrides.clear()

        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()



@pytest.mark.asyncio
async def test_cancelling_queue_entry_broadcasts_token_cancelled_to_display(
    db,
    queue_entry,
    receptionist_token_headers,
):
    """
    End-to-end flow:

    Queue entry exists
        ↓
    Queue entry is cancelled
        ↓
    Backend commits the state
        ↓
    Display receives TOKEN_CANCELLED
    """

    await db.commit()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    try:
        with TestClient(app) as test_client:

            with test_client.websocket_connect(
                "/ws/display"
            ) as websocket:

                # Consume WebSocket handshake.
                connection_event = websocket.receive_json()

                assert connection_event["event_type"] == (
                    "CONNECTION_ESTABLISHED"
                )

                # -------------------------------------------------
                # CANCEL
                # -------------------------------------------------

                response = test_client.patch(
                    f"/api/queue/{queue_entry.queue_entry_id}/cancel",
                    headers=receptionist_token_headers,
                )

                assert response.status_code == 200

                body = response.json()

                assert body["status"] == "CANCELLED"

                # -------------------------------------------------
                # VERIFY DISPLAY EVENT
                # -------------------------------------------------

                event = websocket.receive_json()

                assert event["event_type"] == "TOKEN_CANCELLED"
                assert event["token_number"] == "W-101"
                assert event["dept_id"] == str(
                    queue_entry.dept_id
                )

    finally:
        app.dependency_overrides.clear()
        ws_manager._display_connections.clear()
        ws_manager._staff_connections.clear()