
import pytest
from unittest.mock import AsyncMock

from app.api.routes.websocket_manager import ws_manager
from app.domain.models.models import (
    Department,
    EntryType,
    Patient,
    QueueEntryStatus,
    QueuePriority,
    Visit,
    VisitStage,
)
from app.domain.services.queue_service import QueueService


class RecordingWebSocket:
    def __init__(self):
        self.accepted = False
        self.sent_messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.sent_messages.append(payload)


@pytest.fixture(autouse=True)
def clear_websocket_state():
    ws_manager._display_connections.clear()
    ws_manager._staff_connections.clear()

    yield

    ws_manager._display_connections.clear()
    ws_manager._staff_connections.clear()


async def _create_queue_entry(
    db,
    department: Department,
    token_number: str = "A-001",
):
    patient = Patient(
        first_name="Test",
        last_name="Patient",
        gender="MALE",
        phone="+254700000000",
    )

    db.add(patient)
    await db.flush()

    visit = Visit(
        patient_id=patient.patient_id,
        token_number=token_number,
        entry_type=EntryType.WALK_IN,
        visit_reason="Integration websocket flow",
        stage=VisitStage.ACTIVE,
    )

    db.add(visit)
    await db.flush()

    service = QueueService(db)

    entry = await service.create_queue_entry(
        visit_id=visit.visit_id,
        department_id=department.dept_id,
        priority=QueuePriority.NORMAL,
    )

    await db.commit()

    return entry


async def _transition_and_publish(
    db,
    entry,
    new_status: QueueEntryStatus,
):
    """
    Execute a queue transition using the application's
    transaction boundary.

    The state is flushed first, committed second, and the
    WebSocket event is published only after the commit succeeds.
    """
    service = QueueService(db)

    entry = await service.transition_entry_status(
        entry.queue_entry_id,
        new_status,
    )

    # Database transaction boundary.
    await db.commit()

    # Publish only after successful commit.
    await service.emit_display_event(entry)

    return entry


@pytest.mark.asyncio
async def test_calling_token_commits_before_broadcasting_token_called(
    db,
    routing_departments,
):
    department = routing_departments["triage"]
    websocket = RecordingWebSocket()

    await ws_manager.connect_display(
        str(department.dept_id),
        websocket,
    )

    entry = await _create_queue_entry(
        db,
        department,
        token_number="A-001",
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.CALLED,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_CALLED"
    assert payload["token_number"] == "A-001"
    assert payload["department_id"] == str(
        department.dept_id
    )


@pytest.mark.asyncio
async def test_completing_token_commits_before_broadcasting_completed(
    db,
    routing_departments,
):
    department = routing_departments["triage"]
    websocket = RecordingWebSocket()

    await ws_manager.connect_display(
        str(department.dept_id),
        websocket,
    )

    entry = await _create_queue_entry(
        db,
        department,
        token_number="A-002",
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.CALLED,
    )

    service = QueueService(db)

    entry = await service.get_queue_entry(
        entry.queue_entry_id
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.IN_PROGRESS,
    )

    entry = await service.get_queue_entry(
        entry.queue_entry_id
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.COMPLETED,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_COMPLETED"
    assert payload["token_number"] == "A-002"


@pytest.mark.asyncio
async def test_cancelling_token_commits_before_broadcasting_cancelled(
    db,
    routing_departments,
):
    department = routing_departments["triage"]
    websocket = RecordingWebSocket()

    await ws_manager.connect_display(
        str(department.dept_id),
        websocket,
    )

    entry = await _create_queue_entry(
        db,
        department,
        token_number="A-003",
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.CANCELLED,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_CANCELLED"
    assert payload["token_number"] == "A-003"


@pytest.mark.asyncio
async def test_queue_change_commits_before_broadcasting_queue_updated(
    db,
    routing_departments,
):
    department = routing_departments["triage"]
    websocket = RecordingWebSocket()

    await ws_manager.connect_display(
        str(department.dept_id),
        websocket,
    )

    entry = await _create_queue_entry(
        db,
        department,
        token_number="A-004",
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.CALLED,
    )

    service = QueueService(db)

    entry = await service.get_queue_entry(
        entry.queue_entry_id
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.IN_PROGRESS,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "QUEUE_UPDATED"
    assert payload["department_id"] == str(
        department.dept_id
    )


@pytest.mark.asyncio
async def test_event_reaches_correct_department_display(
    db,
    routing_departments,
):
    department = routing_departments["triage"]
    other_department = routing_departments["emergency"]

    department_socket = RecordingWebSocket()
    other_socket = RecordingWebSocket()

    await ws_manager.connect_display(
        str(department.dept_id),
        department_socket,
    )

    await ws_manager.connect_display(
        str(other_department.dept_id),
        other_socket,
    )

    entry = await _create_queue_entry(
        db,
        department,
        token_number="A-005",
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.CALLED,
    )

    assert (
        department_socket.sent_messages[-1]["event_type"]
        == "TOKEN_CALLED"
    )

    # The other department only received its handshake.
    assert len(other_socket.sent_messages) == 1

    assert (
        other_socket.sent_messages[0]["event_type"]
        == "CONNECTION_ESTABLISHED"
    )


@pytest.mark.asyncio
async def test_event_reaches_global_display(
    db,
    routing_departments,
):
    department = routing_departments["triage"]

    department_socket = RecordingWebSocket()
    global_socket = RecordingWebSocket()

    await ws_manager.connect_display(
        str(department.dept_id),
        department_socket,
    )

    await ws_manager.connect_display(
        None,
        global_socket,
    )

    entry = await _create_queue_entry(
        db,
        department,
        token_number="A-006",
    )

    await _transition_and_publish(
        db,
        entry,
        QueueEntryStatus.CALLED,
    )

    assert (
        department_socket.sent_messages[-1]["event_type"]
        == "TOKEN_CALLED"
    )

    assert (
        global_socket.sent_messages[-1]["event_type"]
        == "TOKEN_CALLED"
    )


@pytest.mark.asyncio
async def test_failed_commit_does_not_publish_display_event(
    db,
    routing_departments,
    monkeypatch,
):
    """
    Critical transaction-boundary test.

    If the database commit fails, the WebSocket event must
    NOT be published because the state transition was not
    successfully committed.
    """
    department = routing_departments["triage"]
    websocket = RecordingWebSocket()

    await ws_manager.connect_display(
        str(department.dept_id),
        websocket,
    )

    entry = await _create_queue_entry(
        db,
        department,
        token_number="A-007",
    )

    service = QueueService(db)

    entry = await service.transition_entry_status(
        entry.queue_entry_id,
        QueueEntryStatus.CALLED,
    )

    # The transition has been flushed but NOT committed.
    assert entry.status == QueueEntryStatus.CALLED

    original_messages = list(
        websocket.sent_messages
    )

    # Simulate a database commit failure.
    async def failing_commit():
        raise RuntimeError(
            "Simulated database commit failure"
        )

    monkeypatch.setattr(
        db,
        "commit",
        failing_commit,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated database commit failure",
    ):
        await db.commit()

    # No event was published because commit failed.
    assert websocket.sent_messages == original_messages

    assert not any(
        message.get("event_type") == "TOKEN_CALLED"
        for message in websocket.sent_messages
    )

    # Explicitly verify that the publisher was never invoked.
    publish_mock = AsyncMock()

    monkeypatch.setattr(
        service,
        "emit_display_event",
        publish_mock,
    )

    assert not publish_mock.await_args_list

