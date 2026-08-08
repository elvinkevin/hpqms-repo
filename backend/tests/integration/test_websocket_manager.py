import pytest

from app.api.routes.websocket_manager import WebSocketManager


# ============================================================================
# Test WebSocket
# ============================================================================

class DummyWebSocket:
    def __init__(self):
        self.accepted = False
        self.sent_messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.sent_messages.append(payload)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def manager():
    return WebSocketManager()


# ============================================================================
# Display Connection Lifecycle
# ============================================================================

@pytest.mark.asyncio
async def test_connect_display_registers_socket_and_sends_connection_event(
    manager,
):
    websocket = DummyWebSocket()

    await manager.connect_display(
        "dept-opd",
        websocket,
    )

    assert websocket.accepted is True

    assert manager._display_connections["dept-opd"] == [
        websocket
    ]

    assert len(websocket.sent_messages) == 1

    payload = websocket.sent_messages[0]

    assert payload["event_type"] == "CONNECTION_ESTABLISHED"
    assert payload["message"] == (
        "Connected to the HPQMS public display stream"
    )
    assert payload["occurred_at"]


@pytest.mark.asyncio
async def test_connect_display_without_department_uses_global_pool(
    manager,
):
    websocket = DummyWebSocket()

    await manager.connect_display(
        None,
        websocket,
    )

    assert manager._display_connections["__all__"] == [
        websocket
    ]


@pytest.mark.asyncio
async def test_disconnect_display_removes_socket(
    manager,
):
    websocket = DummyWebSocket()

    await manager.connect_display(
        "dept-opd",
        websocket,
    )

    manager.disconnect_display(
        "dept-opd",
        websocket,
    )

    assert "dept-opd" not in manager._display_connections


@pytest.mark.asyncio
async def test_disconnect_display_is_safe_for_unknown_socket(
    manager,
):
    websocket = DummyWebSocket()

    manager.disconnect_display(
        "dept-opd",
        websocket,
    )

    assert manager._display_connections == {}


# ============================================================================
# Display Routing
# ============================================================================

@pytest.mark.asyncio
async def test_department_specific_event_reaches_matching_department_only(
    manager,
):
    opd_socket = DummyWebSocket()
    pharmacy_socket = DummyWebSocket()

    await manager.connect_display(
        "dept-opd",
        opd_socket,
    )

    await manager.connect_display(
        "dept-pharmacy",
        pharmacy_socket,
    )

    delivered = await manager.broadcast_token_called(
        department_id="dept-opd",
        token_number="P-014",
        service_point="Counter 2",
        department_name="Outpatient",
    )

    assert delivered == 1

    assert opd_socket.sent_messages[-1]["event_type"] == (
        "TOKEN_CALLED"
    )

    # Pharmacy should only have received the connection handshake.
    assert len(pharmacy_socket.sent_messages) == 1

    assert pharmacy_socket.sent_messages[0]["event_type"] == (
        "CONNECTION_ESTABLISHED"
    )

@pytest.mark.asyncio
async def test_department_event_reaches_department_and_global_displays(
    manager,
):
    department_socket = DummyWebSocket()
    global_socket = DummyWebSocket()

    await manager.connect_display(
        "dept-opd",
        department_socket,
    )

    await manager.connect_display(
        None,
        global_socket,
    )

    delivered = await manager.broadcast_token_called(
        department_id="dept-opd",
        token_number="A-001",
        service_point="Room 1",
    )

    assert delivered == 2

    assert (
        department_socket.sent_messages[-1]["event_type"]
        == "TOKEN_CALLED"
    )

    assert (
        global_socket.sent_messages[-1]["event_type"]
        == "TOKEN_CALLED"
    )


@pytest.mark.asyncio
async def test_global_event_reaches_all_display_boards(
    manager,
):
    opd_socket = DummyWebSocket()
    pharmacy_socket = DummyWebSocket()
    global_socket = DummyWebSocket()

    await manager.connect_display(
        "dept-opd",
        opd_socket,
    )

    await manager.connect_display(
        "dept-pharmacy",
        pharmacy_socket,
    )

    await manager.connect_display(
        None,
        global_socket,
    )

    delivered = await manager.broadcast_announcement_created(
        announcement_id="ann-1",
        message="Please take a seat",
    )

    assert delivered == 3

    assert (
        opd_socket.sent_messages[-1]["event_type"]
        == "ANNOUNCEMENT_CREATED"
    )

    assert (
        pharmacy_socket.sent_messages[-1]["event_type"]
        == "ANNOUNCEMENT_CREATED"
    )

    assert (
        global_socket.sent_messages[-1]["event_type"]
        == "ANNOUNCEMENT_CREATED"
    )


@pytest.mark.asyncio
async def test_multiple_connections_same_department_receive_event(
    manager,
):
    socket_one = DummyWebSocket()
    socket_two = DummyWebSocket()
    socket_three = DummyWebSocket()

    await manager.connect_display(
        "dept-opd",
        socket_one,
    )

    await manager.connect_display(
        "dept-opd",
        socket_two,
    )

    await manager.connect_display(
        "dept-opd",
        socket_three,
    )

    delivered = await manager.broadcast_queue_updated(
        department_id="dept-opd",
        message="Queue updated",
        department_name="Outpatient",
    )

    assert delivered == 3

    assert socket_one.sent_messages[-1]["event_type"] == (
        "QUEUE_UPDATED"
    )

    assert socket_two.sent_messages[-1]["event_type"] == (
        "QUEUE_UPDATED"
    )

    assert socket_three.sent_messages[-1]["event_type"] == (
        "QUEUE_UPDATED"
    )


# ============================================================================
# Dead Connection Handling
# ============================================================================

@pytest.mark.asyncio
async def test_dead_connection_is_removed_from_subscription_group(
    manager,
):
    broken_socket = DummyWebSocket()
    healthy_socket = DummyWebSocket()

    await manager.connect_display(
        None,
        broken_socket,
    )

    await manager.connect_display(
        None,
        healthy_socket,
    )

    async def fail_send(payload):
        raise RuntimeError("socket closed")

    broken_socket.send_json = fail_send

    delivered = await manager.broadcast_display(
        {
            "event_type": "QUEUE_UPDATED"
        }
    )

    assert delivered == 1

    assert manager._display_connections["__all__"] == [
        healthy_socket
    ]


@pytest.mark.asyncio
async def test_dead_connection_does_not_prevent_healthy_connections_from_receiving_event(
    manager,
):
    broken_socket = DummyWebSocket()
    healthy_socket = DummyWebSocket()

    await manager.connect_display(
        "dept-opd",
        broken_socket,
    )

    await manager.connect_display(
        "dept-opd",
        healthy_socket,
    )

    async def fail_send(payload):
        raise RuntimeError("connection lost")

    broken_socket.send_json = fail_send

    delivered = await manager.broadcast_queue_updated(
        department_id="dept-opd",
        message="Queue updated",
    )

    assert delivered == 1

    assert healthy_socket.sent_messages[-1]["event_type"] == (
        "QUEUE_UPDATED"
    )

    assert manager._display_connections["dept-opd"] == [
        healthy_socket
    ]


# ============================================================================
# TOKEN_CALLED
# ============================================================================

@pytest.mark.asyncio
async def test_token_called_payload_contains_expected_fields(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        "dept-pharmacy",
        socket,
    )

    await manager.broadcast_token_called(
        department_id="dept-pharmacy",
        token_number="P-014",
        service_point="Counter 2",
        department_name="Pharmacy",
        message="Token P-014 called to Counter 2",
        priority="HIGH",
    )

    payload = socket.sent_messages[-1]

    assert payload["event_id"]
    assert payload["event_type"] == "TOKEN_CALLED"
    assert payload["priority"] == "HIGH"

    assert payload["department_id"] == "dept-pharmacy"
    assert payload["department_name"] == "Pharmacy"

    assert payload["token_number"] == "P-014"
    assert payload["service_point"] == "Counter 2"

    assert payload["message"] == (
        "Token P-014 called to Counter 2"
    )

    assert payload["occurred_at"]


@pytest.mark.asyncio
async def test_token_called_generates_default_message(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        "dept-pharmacy",
        socket,
    )

    await manager.broadcast_token_called(
        department_id="dept-pharmacy",
        token_number="P-014",
        service_point="Counter 2",
    )

    payload = socket.sent_messages[-1]

    assert payload["message"] == (
        "Token P-014 called to Counter 2"
    )


# ============================================================================
# QUEUE_UPDATED
# ============================================================================

@pytest.mark.asyncio
async def test_queue_updated_payload_contains_expected_fields(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        "dept-pharmacy",
        socket,
    )

    await manager.broadcast_queue_updated(
        department_id="dept-pharmacy",
        message="Queue updated",
        department_name="Pharmacy",
        priority="NORMAL",
    )

    payload = socket.sent_messages[-1]

    assert payload["event_id"]
    assert payload["event_type"] == "QUEUE_UPDATED"
    assert payload["priority"] == "NORMAL"

    assert payload["department_id"] == "dept-pharmacy"
    assert payload["department_name"] == "Pharmacy"

    assert payload["message"] == "Queue updated"
    assert payload["occurred_at"]


# ============================================================================
# TOKEN_COMPLETED
# ============================================================================

@pytest.mark.asyncio
async def test_token_completed_payload_contains_expected_fields(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        "dept-pharmacy",
        socket,
    )

    await manager.broadcast_token_completed(
        department_id="dept-pharmacy",
        token_number="P-014",
        department_name="Pharmacy",
        message="Token P-014 completed",
        priority="NORMAL",
    )

    payload = socket.sent_messages[-1]

    assert payload["event_id"]
    assert payload["event_type"] == "TOKEN_COMPLETED"

    assert payload["department_id"] == "dept-pharmacy"
    assert payload["department_name"] == "Pharmacy"

    assert payload["token_number"] == "P-014"

    assert payload["message"] == (
        "Token P-014 completed"
    )

    assert payload["priority"] == "NORMAL"
    assert payload["occurred_at"]


@pytest.mark.asyncio
async def test_token_completed_generates_default_message(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        "dept-pharmacy",
        socket,
    )

    await manager.broadcast_token_completed(
        department_id="dept-pharmacy",
        token_number="P-014",
    )

    payload = socket.sent_messages[-1]

    assert payload["message"] == (
        "Token P-014 completed"
    )


# ============================================================================
# TOKEN_CANCELLED
# ============================================================================

@pytest.mark.asyncio
async def test_token_cancelled_payload_contains_expected_fields(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        "dept-pharmacy",
        socket,
    )

    await manager.broadcast_token_cancelled(
        department_id="dept-pharmacy",
        token_number="P-014",
        department_name="Pharmacy",
        message="Token P-014 cancelled",
        priority="NORMAL",
    )

    payload = socket.sent_messages[-1]

    assert payload["event_id"]
    assert payload["event_type"] == "TOKEN_CANCELLED"

    assert payload["department_id"] == "dept-pharmacy"
    assert payload["department_name"] == "Pharmacy"

    assert payload["token_number"] == "P-014"

    assert payload["message"] == (
        "Token P-014 cancelled"
    )

    assert payload["priority"] == "NORMAL"
    assert payload["occurred_at"]


@pytest.mark.asyncio
async def test_token_cancelled_generates_default_message(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        "dept-pharmacy",
        socket,
    )

    await manager.broadcast_token_cancelled(
        department_id="dept-pharmacy",
        token_number="P-014",
    )

    payload = socket.sent_messages[-1]

    assert payload["message"] == (
        "Token P-014 cancelled"
    )


# ============================================================================
# ANNOUNCEMENT_CREATED
# ============================================================================

@pytest.mark.asyncio
async def test_announcement_payload_contains_expected_fields(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_display(
        None,
        socket,
    )

    await manager.broadcast_announcement_created(
        announcement_id="ann-1",
        message="Please proceed",
        priority="INFO",
    )

    payload = socket.sent_messages[-1]

    assert payload["event_id"]
    assert payload["event_type"] == "ANNOUNCEMENT_CREATED"

    assert payload["announcement_id"] == "ann-1"

    assert payload["announcement_priority"] == "INFO"
    assert payload["priority"] == "INFO"

    assert payload["message"] == "Please proceed"

    assert payload["starts_at"] is None
    assert payload["expires_at"] is None

    assert payload["occurred_at"]


# ============================================================================
# Staff Connections
# ============================================================================

@pytest.mark.asyncio
async def test_connect_staff_registers_connection(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_staff(
        "staff-001",
        socket,
    )

    assert socket.accepted is True

    assert manager._staff_connections["staff-001"] is socket


@pytest.mark.asyncio
async def test_send_to_staff_delivers_message(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_staff(
        "staff-001",
        socket,
    )

    payload = {
        "event_type": "STAFF_ALERT",
        "message": "Emergency patient waiting",
    }

    delivered = await manager.send_to_staff(
        "staff-001",
        payload,
    )

    assert delivered is True

    assert socket.sent_messages[-1] == payload


@pytest.mark.asyncio
async def test_send_to_unknown_staff_returns_false(
    manager,
):
    payload = {
        "event_type": "STAFF_ALERT"
    }

    delivered = await manager.send_to_staff(
        "staff-does-not-exist",
        payload,
    )

    assert delivered is False


@pytest.mark.asyncio
async def test_staff_socket_is_removed_when_send_fails(
    manager,
):
    socket = DummyWebSocket()

    await manager.connect_staff(
        "staff-001",
        socket,
    )

    async def fail_send(payload):
        raise RuntimeError("socket closed")

    socket.send_json = fail_send

    delivered = await manager.send_to_staff(
        "staff-001",
        {
            "event_type": "STAFF_ALERT"
        },
    )

    assert delivered is False

    assert "staff-001" not in manager._staff_connections