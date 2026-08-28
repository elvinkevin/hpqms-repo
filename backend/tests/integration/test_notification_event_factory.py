from uuid import uuid4

from app.domain.schemas.schemas import (
    NotificationEventType,
    NotificationPriority,
    NotificationTarget,
)
from app.domain.services.notification_event_factory import (
    NotificationEventFactory,
)


class TestTokenCalledEvent:

    def test_token_called_creates_correct_event(self):
        visit_id = uuid4()
        queue_entry_id = uuid4()
        dept_id = uuid4()

        event = NotificationEventFactory.token_called(
            token_number="A-028",
            visit_id=visit_id,
            queue_entry_id=queue_entry_id,
            dept_id=dept_id,
            department_name="Reception",
            service_point="Counter 1",
        )

        assert event.event_type == NotificationEventType.TOKEN_CALLED
        assert event.priority == NotificationPriority.HIGH

        assert event.token_number == "A-028"
        assert event.visit_id == visit_id
        assert event.queue_entry_id == queue_entry_id
        assert event.dept_id == dept_id

        assert event.department_name == "Reception"
        assert event.service_point == "Counter 1"

        assert NotificationTarget.PUBLIC_DISPLAY in event.targets
        assert NotificationTarget.AUDIO_SYSTEM in event.targets

    def test_token_called_generates_message(self):
        event = NotificationEventFactory.token_called(
            token_number="A-028",
        )

        assert "A-028" in event.message
        assert "called" in event.message.lower()

class TestTokenServiceStartedEvent:

    def test_service_started_creates_correct_event(self):
        event = NotificationEventFactory.token_service_started(
            token_number="P-014",
            department_name="Pharmacy",
            service_point="Counter 2",
        )

        assert (
            event.event_type
            == NotificationEventType.TOKEN_SERVICE_STARTED
        )

        assert event.priority == NotificationPriority.NORMAL
        assert event.token_number == "P-014"
        assert event.department_name == "Pharmacy"
        assert event.service_point == "Counter 2"

        assert NotificationTarget.PUBLIC_DISPLAY in event.targets
        assert NotificationTarget.AUDIO_SYSTEM not in event.targets

class TestTokenCompletedEvent:

    def test_token_completed_creates_correct_event(self):
        event = NotificationEventFactory.token_completed(
            token_number="L-009",
            department_name="Laboratory",
        )

        assert (
            event.event_type
            == NotificationEventType.TOKEN_COMPLETED
        )

        assert event.token_number == "L-009"
        assert event.department_name == "Laboratory"

        assert (
            NotificationTarget.PUBLIC_DISPLAY
            in event.targets
        )


class TestPatientRoutedEvent:

    def test_patient_routed_creates_correct_event(self):
        visit_id = uuid4()
        queue_entry_id = uuid4()
        dept_id = uuid4()

        event = NotificationEventFactory.patient_routed(
            token_number="A-028",
            visit_id=visit_id,
            queue_entry_id=queue_entry_id,
            dept_id=dept_id,
            department_name="Triage",
        )

        assert (
            event.event_type
            == NotificationEventType.PATIENT_ROUTED
        )

        assert event.token_number == "A-028"
        assert event.department_name == "Triage"

        assert (
            NotificationTarget.STAFF_DASHBOARD
            in event.targets
        )

        assert (
            NotificationTarget.PUBLIC_DISPLAY
            in event.targets
        )