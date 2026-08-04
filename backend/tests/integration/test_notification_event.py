from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domain.schemas.schemas import (
    NotificationEvent,
    NotificationEventType,
    NotificationPriority,
    NotificationTarget,
)


class TestNotificationEventCreation:

    def test_event_generates_id_automatically(self):
        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
        )

        assert isinstance(event.event_id, UUID)

    def test_event_generates_timestamp_automatically(self):
        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
        )

        assert isinstance(event.occurred_at, datetime)
        assert event.occurred_at.tzinfo is not None

    def test_default_priority_is_normal(self):
        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
        )

        assert event.priority == NotificationPriority.NORMAL

    def test_default_targets_are_empty(self):
        event = NotificationEvent(
            event_type=NotificationEventType.QUEUE_UPDATED,
        )

        assert event.targets == []

    def test_event_accepts_full_token_context(self):
        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            department_name="Reception",
            service_point="Counter 1",
            message="Please proceed to Reception Counter 1",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
                NotificationTarget.AUDIO_SYSTEM,
            ],
        )

        assert event.token_number == "A-028"
        assert event.department_name == "Reception"
        assert event.service_point == "Counter 1"

        assert NotificationTarget.PUBLIC_DISPLAY in event.targets
        assert NotificationTarget.AUDIO_SYSTEM in event.targets

class TestNotificationEventValidation:

    def test_token_number_cannot_exceed_20_characters(self):
        with pytest.raises(ValidationError):
            NotificationEvent(
                event_type=NotificationEventType.TOKEN_CALLED,
                token_number="A" * 21,
            )

    def test_department_name_cannot_exceed_100_characters(self):
        with pytest.raises(ValidationError):
            NotificationEvent(
                event_type=NotificationEventType.TOKEN_CALLED,
                department_name="A" * 101,
            )

    def test_message_cannot_exceed_255_characters(self):
        with pytest.raises(ValidationError):
            NotificationEvent(
                event_type=NotificationEventType.TOKEN_CALLED,
                message="A" * 256,
            )

    def test_invalid_event_type_is_rejected(self):
        with pytest.raises(ValidationError):
            NotificationEvent(
                event_type="INVALID_EVENT",
            )

    def test_invalid_priority_is_rejected(self):
        with pytest.raises(ValidationError):
            NotificationEvent(
                event_type=NotificationEventType.TOKEN_CALLED,
                priority="URGENT",
            )

    def test_invalid_target_is_rejected(self):
        with pytest.raises(ValidationError):
            NotificationEvent(
                event_type=NotificationEventType.TOKEN_CALLED,
                targets=["WHATSAPP"],
            )