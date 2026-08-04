from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID
from collections import deque
from app.domain.schemas.schemas import (
    NotificationEvent,
    NotificationTarget,
)


NotificationHandler = Callable[
    [NotificationEvent],
    Awaitable[None],
]


@dataclass(frozen=True)
class NotificationSubscription:
    handler: NotificationHandler
    department_id: UUID | None = None


class NotificationService:
    """
    Application-level notification dispatcher.

    The service is transport-agnostic. It does not know whether
    notifications are ultimately delivered through WebSockets,
    SSE, audio, mobile clients, or another transport.

    It manages notification events, target channels, and department-scoped subscribers.
    """

    def __init__(
        self,
        *,
        history_limit: int = 100,
    ):
        if history_limit < 1:
            raise ValueError("history_limit must be at least 1")

        self._history_limit = history_limit

        self._history: deque[NotificationEvent] = deque(
            maxlen=history_limit
        )

        self._subscribers: dict[
            NotificationTarget,
            list[NotificationSubscription],
        ] = {
            target: []
            for target in NotificationTarget
        }

    # ---------------------------------------------------------
    # SUBSCRIPTION
    # ---------------------------------------------------------

    def subscribe(
        self,
        target: NotificationTarget,
        handler: NotificationHandler,
        *,
        department_id: UUID | None = None,
    ) -> None:
        """
        Register a notification handler.

        If department_id is supplied, the handler only receives
        events belonging to that department.
        """

        subscription = NotificationSubscription(
            handler=handler,
            department_id=department_id,
        )

        if subscription not in self._subscribers[target]:
            self._subscribers[target].append(subscription)

    def unsubscribe(
        self,
        target: NotificationTarget,
        handler: NotificationHandler,
        *,
        department_id: UUID | None = None,
    ) -> None:
        """
        Remove a previously registered handler for a specific target and scope.
        """

        subscription = NotificationSubscription(
            handler=handler,
            department_id=department_id,
        )

        if subscription in self._subscribers[target]:
            self._subscribers[target].remove(subscription)

    # ---------------------------------------------------------
    # DISPATCH
    # ---------------------------------------------------------

    async def publish(
        self,
        event: NotificationEvent,
    ) -> None:
        """
        Store and publish a notification event.
        """

        self._history.append(event)

        subscriptions: list[NotificationSubscription] = []

        for target in event.targets:
            subscriptions.extend(
                self._subscribers.get(target, [])
            )

        unique_subscriptions = list(
            dict.fromkeys(subscriptions)
        )

        for subscription in unique_subscriptions:

            if subscription.department_id is None:
                await subscription.handler(event)
                continue

            if event.department_id == subscription.department_id:
                await subscription.handler(event)

    # ---------------------------------------------------------
    # INSPECTION
    # ---------------------------------------------------------

    def subscriber_count(
        self,
        target: NotificationTarget,
    ) -> int:
        """
        Return the number of subscribers for a target.
        """

        return len(self._subscribers[target])

    def total_subscribers(self) -> int:
        """
        Return the total number of registered subscribers across all targets.
        """

        return sum(
            len(handlers)
            for handlers in self._subscribers.values()
        )

    def clear_subscribers(self) -> None:
        """
        Remove all subscribers.

        Primarily useful for testing and application shutdown.
        """

        for handlers in self._subscribers.values():
            handlers.clear()
    def get_history(
        self,
        *,
        limit: int | None = None,
    ) -> list[NotificationEvent]:
        """
        Return recent notification events, newest first.
        """

        events = list(reversed(self._history))

        if limit is None:
            return events

        if limit < 1:
            return []

        return events[:limit]

    def get_history_for_department(
        self,
        department_id: UUID,
        *,
        limit: int | None = None,
    ) -> list[NotificationEvent]:
        """
        Return recent events belonging to a specific department.
        """

        events = [
            event
            for event in reversed(self._history)
            if event.department_id == department_id
        ]

        if limit is None:
            return events

        if limit < 1:
            return []

        return events[:limit]

    def clear_history(self) -> None:
        """
        Clear all retained notification history.
        """

        self._history.clear()
    def history_count(self) -> int:
        """
        Return the number of currently retained events.
        """

        return len(self._history)