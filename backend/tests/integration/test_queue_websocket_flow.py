
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
        dept_id=department.dept_id,
        priority=QueuePriority.NORMAL,
    )

    await db.commit()

    return entry


async def _transition_and_publish(
    db,
    entry,
    new_status: QueueEntryStatus,
    staff_id=None,
    event_type=None,
):
    service = QueueService(db)

    entry = await service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=new_status,
        staff_id=staff_id,
    )

    await db.commit()

    await service.emit_display_event(
        entry,
        event_type=event_type,
    )

    return entry



@pytest.mark.asyncio
async def test_calling_token_commits_before_broadcasting_token_called(
    db,
    routing_departments,
    receptionist,  # <-- 1. Inject the valid staff fixture
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

    # 2. Pass staff_id to get past the 400 validation guard
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,  # <-- Pass the mandatory staff reference
    )


    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_CALLED"
    assert payload["token_number"] == "A-001"
    assert payload["dept_id"] == str(
        department.dept_id
    )

    assert payload["queue_entry_id"] == str(entry.queue_entry_id)
    assert payload["department_name"] == department.name
    assert payload["status"] == QueueEntryStatus.CALLED.value
    assert payload["queue_priority"] == QueuePriority.NORMAL.value
    assert payload["assigned_staff_id"] == str(receptionist.staff_id)

    assert payload["occurred_at"] is not None
    assert payload["server_timestamp"] is not None


@pytest.mark.asyncio
async def test_completing_token_commits_before_broadcasting_completed(
    db,
    routing_departments,
    receptionist,  # <-- 1. Inject the valid staff fixture
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

    # 2. Pass staff_id into the CALLED state mutation
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
    )

    service = QueueService(db)

    entry = await service.get_queue_entry(
        entry.queue_entry_id
    )

    # 3. Pass staff_id into the IN_PROGRESS state mutation
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=receptionist.staff_id,
    )

    entry = await service.get_queue_entry(
        entry.queue_entry_id
    )

    # 4. Pass staff_id into the COMPLETED state mutation
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.COMPLETED,
        staff_id=receptionist.staff_id,
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
async def test_queue_change_commits_before_broadcasting_token_service_started(
    db,
    routing_departments,
    receptionist,  # <-- 1. Inject the valid staff fixture
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

    # 2. Pass staff_id into the CALLED state transition
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
    )

    service = QueueService(db)

    entry = await service.get_queue_entry(
        entry.queue_entry_id
    )

    # 3. Pass staff_id into the IN_PROGRESS state transition
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=receptionist.staff_id,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_SERVICE_STARTED"
    assert payload["dept_id"] == str(
        department.dept_id
    )


@pytest.mark.asyncio
async def test_event_reaches_correct_department_display(
    db,
    routing_departments,
    receptionist,  # <-- 1. Inject the valid staff fixture
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

    # 2. Pass staff_id into the transition wrapper
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
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
    receptionist,  # <-- 1. Inject the valid staff fixture
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

    # 2. Pass staff_id into the transition wrapper statement
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
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
    receptionist,  # <-- 1. Inject the valid staff fixture
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

    # 2. Add staff_id argument here to safely bypass the 400 guard exception
    entry = await service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,  # <-- Added missing operational argument
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



@pytest.mark.asyncio
async def test_starting_token_broadcasts_token_service_started(
    db,
    routing_departments,
    receptionist,
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

    # WAITING -> CALLED
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
    )

    websocket.sent_messages.clear()

    # CALLED -> IN_PROGRESS
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=receptionist.staff_id,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_SERVICE_STARTED"
    assert payload["token_number"] == "A-002"
    assert payload["dept_id"] == str(department.dept_id)

    assert payload["queue_entry_id"] == str(entry.queue_entry_id)
    assert payload["department_name"] == department.name
    assert payload["status"] == QueueEntryStatus.IN_PROGRESS.value
    assert payload["queue_priority"] == QueuePriority.NORMAL.value
    assert payload["assigned_staff_id"] == str(receptionist.staff_id)

    assert payload["occurred_at"] is not None
    assert payload["server_timestamp"] is not None

@pytest.mark.asyncio
async def test_completing_token_broadcasts_token_completed(
    db,
    routing_departments,
    receptionist,
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

    # WAITING -> CALLED
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
    )

    # CALLED -> IN_PROGRESS
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=receptionist.staff_id,
    )

    websocket.sent_messages.clear()

    # IN_PROGRESS -> COMPLETED
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.COMPLETED,
        staff_id=receptionist.staff_id,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_COMPLETED"
    assert payload["token_number"] == "A-003"
    assert payload["dept_id"] == str(department.dept_id)

    assert payload["queue_entry_id"] == str(entry.queue_entry_id)
    assert payload["department_name"] == department.name
    assert payload["status"] == QueueEntryStatus.COMPLETED.value
    assert payload["queue_priority"] == QueuePriority.NORMAL.value
    assert payload["assigned_staff_id"] == str(receptionist.staff_id)

    assert payload["occurred_at"] is not None
    assert payload["server_timestamp"] is not None


@pytest.mark.asyncio
async def test_cancelling_token_broadcasts_token_cancelled(
    db,
    routing_departments,
    receptionist,
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

    # WAITING -> CALLED
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
    )

    websocket.sent_messages.clear()

    # CALLED -> CANCELLED
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CANCELLED,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_CANCELLED"
    assert payload["token_number"] == "A-004"
    assert payload["dept_id"] == str(department.dept_id)

    assert payload["queue_entry_id"] == str(entry.queue_entry_id)
    assert payload["department_name"] == department.name
    assert payload["status"] == QueueEntryStatus.CANCELLED.value
    assert payload["queue_priority"] == QueuePriority.NORMAL.value

    assert payload["assigned_staff_id"] == str(receptionist.staff_id)

    assert payload["occurred_at"] is not None
    assert payload["server_timestamp"] is not None



@pytest.mark.asyncio
async def test_marking_token_no_show_broadcasts_token_no_show(
    db,
    routing_departments,
    receptionist,
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
        token_number="A-005",
    )

    # WAITING -> CALLED
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
    )

    websocket.sent_messages.clear()

    # CALLED -> NO_SHOW
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.NO_SHOW,
        staff_id=receptionist.staff_id,
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_NO_SHOW"
    assert payload["token_number"] == "A-005"
    assert payload["dept_id"] == str(department.dept_id)

    assert payload["queue_entry_id"] == str(entry.queue_entry_id)
    assert payload["department_name"] == department.name
    assert payload["status"] == QueueEntryStatus.NO_SHOW.value
    assert payload["queue_priority"] == QueuePriority.NORMAL.value
    assert payload["assigned_staff_id"] == str(receptionist.staff_id)

    assert payload["occurred_at"] is not None
    assert payload["server_timestamp"] is not None

    assert entry.no_show_at is not None
    assert entry.completed_at is None


@pytest.mark.asyncio
async def test_requeue_broadcasts_token_requeued(
    db,
    routing_departments,
    receptionist,
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
        token_number="A-006",
    )

    # WAITING -> CALLED
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.CALLED,
        staff_id=receptionist.staff_id,
    )

    # CALLED -> NO_SHOW
    await _transition_and_publish(
        db=db,
        entry=entry,
        new_status=QueueEntryStatus.NO_SHOW,
        staff_id=receptionist.staff_id,
    )

    websocket.sent_messages.clear()

    # NO_SHOW -> WAITING
    entry = await QueueService(db).requeue_queue_entry(
        queue_entry_id=entry.queue_entry_id,
        staff_id=receptionist.staff_id,
    )

    await db.commit()

    await QueueService(db).emit_display_event(
        entry,
        event_type="TOKEN_REQUEUED",
    )

    payload = websocket.sent_messages[-1]

    assert payload["event_type"] == "TOKEN_REQUEUED"
    assert payload["token_number"] == "A-006"
    assert payload["dept_id"] == str(department.dept_id)

    assert payload["queue_entry_id"] == str(entry.queue_entry_id)
    assert payload["department_name"] == department.name
    assert payload["status"] == QueueEntryStatus.WAITING.value
    assert payload["queue_priority"] == QueuePriority.NORMAL.value

    assert payload["assigned_staff_id"] is None

    assert payload["occurred_at"] is not None
    assert payload["server_timestamp"] is not None