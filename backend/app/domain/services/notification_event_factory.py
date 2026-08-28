from datetime import datetime, timezone
from uuid import UUID

from app.domain.models.models import QueueEntryStatus
from app.domain.schemas.schemas import (
    NotificationEvent,
    NotificationEventType,
    NotificationPriority,
    NotificationTarget,
)


class NotificationEventFactory:
    """
    Creates standardized notification events from HPQMS domain actions.

    This class does not send notifications.
    It only translates domain events into NotificationEvent payloads.
    """

    @staticmethod
    def token_called(
        *,
        token_number: str,
        visit_id: UUID | None = None,
        queue_entry_id: UUID | None = None,
        dept_id: UUID | None = None,
        department_name: str | None = None,
        service_point: str | None = None,
    ) -> NotificationEvent:

        return NotificationEvent(
            event_type=NotificationEventType.TOKEN_CALLED,
            priority=NotificationPriority.HIGH,

            token_number=token_number,
            visit_id=visit_id,
            queue_entry_id=queue_entry_id,

            dept_id=dept_id,
            department_name=department_name,
            service_point=service_point,

            message=(
                f"Token {token_number} has been called."
            ),

            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
                NotificationTarget.AUDIO_SYSTEM,
            ],
        )

    @staticmethod
    def token_service_started(
        *,
        token_number: str,
        visit_id: UUID | None = None,
        queue_entry_id: UUID | None = None,
        dept_id: UUID | None = None,
        department_name: str | None = None,
        service_point: str | None = None,
    ) -> NotificationEvent:

        return NotificationEvent(
            event_type=NotificationEventType.TOKEN_SERVICE_STARTED,
            priority=NotificationPriority.NORMAL,

            token_number=token_number,
            visit_id=visit_id,
            queue_entry_id=queue_entry_id,

            dept_id=dept_id,
            department_name=department_name,
            service_point=service_point,

            message=(
                f"Token {token_number} is now being served."
            ),

            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

    @staticmethod
    def token_completed(
        *,
        token_number: str,
        visit_id: UUID | None = None,
        queue_entry_id: UUID | None = None,
        dept_id: UUID | None = None,
        department_name: str | None = None,
    ) -> NotificationEvent:

        return NotificationEvent(
            event_type=NotificationEventType.TOKEN_COMPLETED,
            priority=NotificationPriority.NORMAL,

            token_number=token_number,
            visit_id=visit_id,
            queue_entry_id=queue_entry_id,

            dept_id=dept_id,
            department_name=department_name,

            message=(
                f"Token {token_number} has completed service."
            ),

            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

    @staticmethod
    def token_no_show(
        *,
        token_number: str,
        visit_id: UUID | None = None,
        queue_entry_id: UUID | None = None,
        dept_id: UUID | None = None,
        department_name: str | None = None,
    ) -> NotificationEvent:

        return NotificationEvent(
            event_type=NotificationEventType.TOKEN_NO_SHOW,
            priority=NotificationPriority.HIGH,

            token_number=token_number,
            visit_id=visit_id,
            queue_entry_id=queue_entry_id,

            dept_id=dept_id,
            department_name=department_name,

            message=(
                f"Token {token_number} was marked as no-show."
            ),

            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

    @staticmethod
    def patient_routed(
        *,
        token_number: str,
        visit_id: UUID,
        queue_entry_id: UUID,
        dept_id: UUID,
        department_name: str,
    ) -> NotificationEvent:

        return NotificationEvent(
            event_type=NotificationEventType.PATIENT_ROUTED,
            priority=NotificationPriority.NORMAL,

            token_number=token_number,
            visit_id=visit_id,
            queue_entry_id=queue_entry_id,

            dept_id=dept_id,
            department_name=department_name,

            message=(
                f"Token {token_number} has been routed to "
                f"{department_name}."
            ),

            targets=[
                NotificationTarget.STAFF_DASHBOARD,
                NotificationTarget.PUBLIC_DISPLAY,
            ],
        )

    @staticmethod
    def queue_updated(
        *,
        dept_id: UUID,
        department_name: str | None = None,
    ) -> NotificationEvent:

        return NotificationEvent(
            event_type=NotificationEventType.QUEUE_UPDATED,
            priority=NotificationPriority.LOW,

            dept_id=dept_id,
            department_name=department_name,

            targets=[
                NotificationTarget.PUBLIC_DISPLAY,
                NotificationTarget.STAFF_DASHBOARD,
            ],
        )