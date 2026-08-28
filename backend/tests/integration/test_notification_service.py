import pytest

from app.domain.schemas.schemas import NotificationTarget
from app.domain.services.notification_service import (
    NotificationService,
)
from uuid import uuid4

from app.domain.schemas.schemas import (
    NotificationEvent,
    NotificationEventType,
    NotificationPriority,
    NotificationTarget,
)

class TestNotificationSubscription:

    def test_subscriber_can_be_registered(self):
        service = NotificationService()

        async def handler(event):
            pass

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        assert (
            service.subscriber_count(
                NotificationTarget.PUBLIC_DISPLAY
            )
            == 1
        )

    def test_same_handler_is_not_registered_twice(self):
        service = NotificationService()

        async def handler(event):
            pass

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        assert (
            service.subscriber_count(
                NotificationTarget.PUBLIC_DISPLAY
            )
            == 1
        )

    def test_subscriber_can_be_removed(self):
        service = NotificationService()

        async def handler(event):
            pass

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        service.unsubscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        assert (
            service.subscriber_count(
                NotificationTarget.PUBLIC_DISPLAY
            )
            == 0
        )

    def test_unsubscribing_unknown_handler_is_safe(self):
        service = NotificationService()

        async def handler(event):
            pass

        service.unsubscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        assert (
            service.subscriber_count(
                NotificationTarget.PUBLIC_DISPLAY
            )
            == 0
        )

class TestNotificationPublishing:

    @pytest.mark.asyncio
    async def test_publish_delivers_event_to_subscriber(self):
        service = NotificationService()

        received_events = []

        async def handler(event):
            received_events.append(event)

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(event)

        assert len(received_events) == 1
        assert received_events[0] == event

    @pytest.mark.asyncio
    async def test_publish_does_not_notify_unrelated_target(self):
        service = NotificationService()

        display_events = []
        audio_events = []

        async def display_handler(event):
            display_events.append(event)

        async def audio_handler(event):
            audio_events.append(event)

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            display_handler,
        )

        service.subscribe(
            NotificationTarget.AUDIO_SYSTEM,
            audio_handler,
        )

        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(event)

        assert len(display_events) == 1
        assert len(audio_events) == 0

    @pytest.mark.asyncio
    async def test_publish_delivers_to_multiple_targets(self):
        service = NotificationService()

        display_events = []
        audio_events = []

        async def display_handler(event):
            display_events.append(event)

        async def audio_handler(event):
            audio_events.append(event)

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            display_handler,
        )

        service.subscribe(
            NotificationTarget.AUDIO_SYSTEM,
            audio_handler,
        )

        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
                NotificationTarget.AUDIO_SYSTEM,
            ],
        )

        await service.publish(event)

        assert len(display_events) == 1
        assert len(audio_events) == 1

        assert display_events[0].token_number == "A-028"
        assert audio_events[0].token_number == "A-028"

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive_same_event(self):
        service = NotificationService()

        first_client = []
        second_client = []

        async def first_handler(event):
            first_client.append(event)

        async def second_handler(event):
            second_client.append(event)

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            first_handler,
        )

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            second_handler,
        )

        event = NotificationEvent(
            event_type=NotificationEventType.QUEUE_UPDATED,
            priority=NotificationPriority.LOW,
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(event)

        assert len(first_client) == 1
        assert len(second_client) == 1

        assert first_client[0] == event
        assert second_client[0] == event

    @pytest.mark.asyncio
    async def test_publish_with_no_subscribers_is_safe(self):
        service = NotificationService()

        event = NotificationEvent(
            event_type=NotificationEventType.QUEUE_UPDATED,
            priority=NotificationPriority.LOW,
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(event)

    @pytest.mark.asyncio
    async def test_same_subscriber_receives_event_only_once(self):
        service = NotificationService()

        received_events = []

        async def handler(event):
            received_events.append(event)

        service.subscribe(
            NotificationTarget.PUBLIC_DISPLAY,
            handler,
        )

        event = NotificationEvent(
            event_type=NotificationEventType.QUEUE_UPDATED,
            priority=NotificationPriority.LOW,
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(event)

        assert len(received_events) == 1

@pytest.mark.asyncio
async def test_department_subscriber_receives_matching_event():
    service = NotificationService()

    pharmacy_id = uuid4()
    received = []

    async def handler(event):
        received.append(event)

    service.subscribe(
        NotificationTarget.PUBLIC_DISPLAY,
        handler,
        dept_id=pharmacy_id,
    )

    event = NotificationEvent(
        event_type=NotificationEventType.TOKEN_CALLED,
        priority=NotificationPriority.HIGH,
        token_number="P-014",
        dept_id=pharmacy_id,
        targets=[
            NotificationTarget.PUBLIC_DISPLAY,
        ],
    )

    await service.publish(event)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_department_subscriber_ignores_other_department():
    service = NotificationService()

    pharmacy_id = uuid4()
    reception_id = uuid4()

    received = []

    async def handler(event):
        received.append(event)

    service.subscribe(
        NotificationTarget.PUBLIC_DISPLAY,
        handler,
        dept_id=pharmacy_id,
    )

    event = NotificationEvent(
        event_type=NotificationEventType.TOKEN_CALLED,
        priority=NotificationPriority.HIGH,
        token_number="A-028",
        dept_id=reception_id,
        targets=[
            NotificationTarget.PUBLIC_DISPLAY,
        ],
    )

    await service.publish(event)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_global_subscriber_receives_all_departments():
    service = NotificationService()

    received = []

    async def handler(event):
        received.append(event)

    service.subscribe(
        NotificationTarget.PUBLIC_DISPLAY,
        handler,
    )

    event = NotificationEvent(
        event_type=NotificationEventType.TOKEN_CALLED,
        priority=NotificationPriority.HIGH,
        token_number="P-014",
        dept_id=uuid4(),
        targets=[
            NotificationTarget.PUBLIC_DISPLAY,
        ],
    )

    await service.publish(event)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_global_and_department_subscribers_can_coexist():
    service = NotificationService()

    pharmacy_id = uuid4()

    global_events = []
    pharmacy_events = []

    async def global_handler(event):
        global_events.append(event)

    async def pharmacy_handler(event):
        pharmacy_events.append(event)

    service.subscribe(
        NotificationTarget.PUBLIC_DISPLAY,
        global_handler,
    )

    service.subscribe(
        NotificationTarget.PUBLIC_DISPLAY,
        pharmacy_handler,
        dept_id=pharmacy_id,
    )

    event = NotificationEvent(
        event_type=NotificationEventType.TOKEN_CALLED,
        priority=NotificationPriority.HIGH,
        token_number="P-014",
        dept_id=pharmacy_id,
        targets=[
            NotificationTarget.PUBLIC_DISPLAY,
        ],
    )

    await service.publish(event)

    assert len(global_events) == 1
    assert len(pharmacy_events) == 1


@pytest.mark.asyncio
async def test_department_subscriber_does_not_receive_other_department_events():
    service = NotificationService()

    pharmacy_id = uuid4()
    reception_id = uuid4()

    pharmacy_events = []

    async def pharmacy_handler(event):
        pharmacy_events.append(event)

    service.subscribe(
        NotificationTarget.PUBLIC_DISPLAY,
        pharmacy_handler,
        dept_id=pharmacy_id,
    )

    reception_event = NotificationEvent(
        event_type=NotificationEventType.TOKEN_CALLED,
        priority=NotificationPriority.HIGH,
        token_number="A-028",
        dept_id=reception_id,
        targets=[
            NotificationTarget.PUBLIC_DISPLAY,
        ],
    )

    await service.publish(reception_event)

    assert pharmacy_events == []


class TestNotificationHistory:

    @pytest.mark.asyncio
    async def test_published_event_is_added_to_history(self):
        service = NotificationService()

        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(event)

        history = service.get_history()

        assert len(history) == 1
        assert history[0] == event
    @pytest.mark.asyncio
    async def test_history_returns_newest_events_first(self):
        service = NotificationService()

        first = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        second = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-029",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(first)
        await service.publish(second)

        history = service.get_history()

        assert history[0].token_number == "A-029"
        assert history[1].token_number == "A-028"

    @pytest.mark.asyncio
    async def test_history_respects_configured_limit(self):
        service = NotificationService(history_limit=2)

        for token in ["A-028", "A-029", "A-030"]:
            event = NotificationEvent(
                event_type=NotificationEventType.TOKEN_CALLED,
                priority=NotificationPriority.HIGH,
                token_number=token,
                targets=[
                    NotificationTarget.PUBLIC_DISPLAY,
                ],
            )

            await service.publish(event)

        history = service.get_history()

        assert len(history) == 2

        assert history[0].token_number == "A-030"
        assert history[1].token_number == "A-029"


    @pytest.mark.asyncio
    async def test_get_history_respects_requested_limit(self):
        service = NotificationService()

        for token in ["A-028", "A-029", "A-030"]:
            event = NotificationEvent(
                event_type=NotificationEventType.TOKEN_CALLED,
                priority=NotificationPriority.HIGH,
                token_number=token,
                targets=[
                    NotificationTarget.PUBLIC_DISPLAY,
                ],
            )

            await service.publish(event)

        history = service.get_history(limit=2)

        assert len(history) == 2
        assert history[0].token_number == "A-030"
        assert history[1].token_number == "A-029"

    @pytest.mark.asyncio
    async def test_department_history_filters_events(self):
        service = NotificationService()

        pharmacy_id = uuid4()
        reception_id = uuid4()

        pharmacy_event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="P-014",
            dept_id=pharmacy_id,
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        reception_event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            dept_id=reception_id,
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(pharmacy_event)
        await service.publish(reception_event)

        history = service.get_history_for_department(
            pharmacy_id
        )

        assert len(history) == 1
        assert history[0].token_number == "P-014"


    @pytest.mark.asyncio
    async def test_clear_history_removes_all_events(self):
        service = NotificationService()

        event = NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,
            token_number="A-028",
            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

        await service.publish(event)

        assert service.history_count() == 1

        service.clear_history()

        assert service.history_count() == 0
        assert service.get_history() == []


   