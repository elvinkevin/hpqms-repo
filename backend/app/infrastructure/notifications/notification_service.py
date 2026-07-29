"""
notification_service.py

Implements the chain-of-responsibility notification pattern.

How it works:
  NotificationService.notify() is the single public method.
  It accepts an event type and resolves which channels to try,
  in which order, and with what recipient per channel.

  It tries channel 1. If it succeeds, it still fires channel 2 onwards
  if they are marked fire_always=True (display board always updates
  regardless of SMS success). If channel 1 fails, it moves to channel 2.

  Every attempt — success or failure — is written to the notifications
  table in the database so ops can audit delivery rates.

Pre-built event types (add more as phases grow):
  TOKEN_ISSUED       patient SMS + display board update
  TOKEN_CALLED       patient SMS + PA announcement + display board
  TRIAGE_REMINDER    nurse dashboard alert
  CHARGE_NURSE_ALERT charge nurse dashboard alert
  TOKEN_COMPLETED    patient SMS (discharge summary)
  PA_ONLY            PA announcement only (no SMS)
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import Notification
from app.infrastructure.notifications.channels import (
    SmsChannel, DashboardChannel, PaChannel, DisplayBoardChannel, ChannelResult,
)

logger = logging.getLogger(__name__)

# Singletons — one instance per channel (cheap, stateless)
_sms       = SmsChannel()
_dashboard = DashboardChannel()
_pa        = PaChannel()
_display   = DisplayBoardChannel()

MAX_RETRIES = 3


class NotificationService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Public API ────────────────────────────────────────────────────────

    async def notify(
        self,
        event:          str,
        patient_phone:  Optional[str] = None,
        patient_name:   Optional[str] = None,
        token_number:   Optional[str] = None,
        dept_id:        Optional[str] = None,
        staff_id:       Optional[str] = None,
        room:           Optional[str] = None,
        estimated_wait: Optional[int] = None,
        token_id:       Optional[UUID] = None,
        patient_id:     Optional[UUID] = None,
        extra:          Optional[dict] = None,
    ) -> list[ChannelResult]:
        """
        Fire all notifications for a given event type.
        Returns list of ChannelResult (one per channel attempted).
        """
        ctx = {
            "patient_name":   patient_name   or "",
            "token_number":   token_number   or "",
            "dept_id":        dept_id        or "",
            "staff_id":       staff_id       or "",
            "room":           room           or "",
            "estimated_wait": estimated_wait or 0,
            **(extra or {}),
        }

        steps = self._resolve_steps(event, ctx, patient_phone)
        results: list[ChannelResult] = []

        for step in steps:
            channel, recipient, message, fire_always = step

            # Attempt with retries
            result, attempts = await self._attempt_with_retry(channel, recipient, message)
            result.attempts = attempts
            results.append(result)

            # Log to DB
            await self._log(
                token_id=token_id, patient_id=patient_id,
                channel=channel.name, message=message, result=result,
                attempts_made=attempts,
            )

            # If failed and not fire_always — stop the chain
            if not result.success and not fire_always:
                logger.info("Notification chain stopped at %s — no further channels.", channel.name)
                break

        return results

    # ── Event → channel steps resolver ───────────────────────────────────

    def _resolve_steps(self, event: str, ctx: dict, phone: Optional[str]):
        """
        Returns a list of (channel, recipient, message, fire_always) tuples.
        fire_always=True means the channel fires even if a previous one succeeded.
        """
        name  = ctx["patient_name"]
        token = ctx["token_number"]
        wait  = ctx["estimated_wait"]
        room  = ctx["room"]
        dept  = ctx["dept_id"]
        staff = ctx["staff_id"]

        if event == "TOKEN_ISSUED":
            return [
                (_sms,     phone or "", f"Hello {name}, your queue token is {token}. Estimated wait: ~{wait} min. Please keep this SMS.", False),
                (_display, dept,        f"New token {token} added to queue.", True),
            ]

        if event == "TOKEN_CALLED":
            return [
                (_sms,     phone or "", f"Hello {name}, it is your turn. Please proceed to {room} now. Token: {token}.", False),
                (_pa,      dept,        f"Token {token}, {name}, please proceed to {room}.", True),
                (_display, dept,        f"Token {token} called to {room}.", True),
            ]

        if event == "TOKEN_COMPLETED":
            return [
                (_sms, phone or "", f"Hello {name}, your visit is complete. Thank you for visiting us today. Token: {token}.", False),
            ]

        if event == "TRIAGE_REMINDER":
            return [
                (_dashboard, staff, f"REMINDER: Unconfirmed triage for token {token}. Please review.", False),
            ]

        if event == "PA_ANNOUNCEMENT":
            return [
                (_pa, dept, ctx.get("pa_text", f"Token {token}, please proceed to reception."), False),
            ]

        if event == "CHARGE_NURSE_ALERT":
            return [
                (_dashboard, staff, f"URGENT: Token {token} has not been triaged for over 90 seconds. Immediate review required.", False),
            ]

        if event == "TOKEN_TRANSFERRED":
            return [
                (_sms, phone or "",
                 f"Hello {name}, you have been referred to another department. Your new token is {token}. Estimated wait: ~{wait} min.",
                 False),
                (_display, dept, f"Token {token} transferred in.", True),
            ]

        logger.warning("Unknown notification event type: %s", event)
        return []

    # ── Retry logic ───────────────────────────────────────────────────────

    async def _attempt_with_retry(self, channel, recipient: str, message: str) -> tuple[ChannelResult, int]:
        last_result = None
        for attempt in range(1, MAX_RETRIES + 1):
            result = await channel.send(recipient, message)
            if result.success:
                return result, attempt
            last_result = result
            if attempt < MAX_RETRIES:
                logger.info(
                    "%s delivery attempt %d/%d failed for %s — retrying.",
                    channel.name, attempt, MAX_RETRIES, recipient,
                )
        return last_result, MAX_RETRIES

    # ── DB logging ────────────────────────────────────────────────────────

    async def _log(
        self,
        token_id:   Optional[UUID],
        patient_id: Optional[UUID],
        channel:    str,
        message:    str,
        result:     ChannelResult,
        attempts_made: int,
    ) -> None:
        entry = Notification(
            token_id    = token_id,
            patient_id  = patient_id,
            channel     = channel,
            message     = message,
            status      = "SENT" if result.success else "FAILED",
            sent_at     = datetime.now(timezone.utc) if result.success else None,
            retry_count = attempts_made - 1,
        )
        self.db.add(entry)
        # Caller's transaction handles flush/commit
