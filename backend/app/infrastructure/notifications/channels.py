"""
channels.py

One class per notification channel. Each implements the same interface:
    async def send(recipient, message, **kwargs) -> ChannelResult

Channels:
  SmsChannel          — Africa's Talking HTTP API
  DashboardChannel    — In-memory event bus (WebSocket server picks these up)
  PaChannel           — HTTP POST to the PA controller device on the LAN
  DisplayBoardChannel — Writes to the shared queue state (WebSocket broadcast)

All channels return a ChannelResult so the NotificationChain knows
whether to continue down the chain or stop.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────

@dataclass
class ChannelResult:
    channel:   str
    success:   bool
    recipient: str
    message:   str
    error:     Optional[str] = None
    metadata:  dict = field(default_factory=dict)
    attempts:  int = 0


# ── Base ──────────────────────────────────────────────────────────────────

class BaseChannel:
    name: str = "base"

    async def send(self, recipient: str, message: str, **kwargs) -> ChannelResult:
        raise NotImplementedError


# ── 1. SMS via Africa's Talking ───────────────────────────────────────────

class SmsChannel(BaseChannel):
    """
    Sends SMS using the Africa's Talking REST API.

    Africa's Talking is Kenya's most reliable SMS gateway.
    Sandbox mode (username="sandbox") is free for testing — no SIM needed.
    Switch to your real username + API key for production.

    AT endpoint: POST https://api.africastalking.com/version1/messaging
    Docs: https://developers.africastalking.com/docs/sms/sending
    """
    name = "SMS"
    BASE_URL = "https://api.africastalking.com/version1/messaging"

    def __init__(self):
        self.api_key  = settings.AFRICAS_TALKING_API_KEY
        self.username = settings.AFRICAS_TALKING_USERNAME

    async def send(self, recipient: str, message: str, **kwargs) -> ChannelResult:
        if not self.api_key:
            logger.warning("SMS: AFRICAS_TALKING_API_KEY not set — skipping.")
            return ChannelResult(
                channel="SMS", success=False,
                recipient=recipient, message=message,
                error="API key not configured",
            )

        # AT requires E.164 format: +2547XXXXXXXX
        phone = self._normalise_phone(recipient)

        payload = {
            "username": self.username,
            "to":       phone,
            "message":  message,
        }
        headers = {
            "apiKey":       self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept":       "application/json",
        }

        try:
            timeout = httpx.Timeout(5.0, connect=2.0, read=5.0, write=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self.BASE_URL, data=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()

            # AT returns SMSMessageData.Recipients[0].status = "Success"
            recipients = body.get("SMSMessageData", {}).get("Recipients", [])
            at_status  = recipients[0].get("status", "") if recipients else ""
            success    = at_status == "Success"

            logger.info("SMS to %s — AT status: %s", phone, at_status)
            return ChannelResult(
                channel="SMS", success=success,
                recipient=phone, message=message,
                error=None if success else f"AT status: {at_status}",
                metadata={"at_response": body},
            )

        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error("SMS HTTP error to %s: %s", phone, error)
            return ChannelResult(channel="SMS", success=False,
                                 recipient=phone, message=message, error=error)

        except Exception as exc:
            logger.error("SMS unexpected error to %s: %s", phone, exc)
            return ChannelResult(channel="SMS", success=False,
                                 recipient=phone, message=message, error=str(exc))

    @staticmethod
    def _normalise_phone(phone: str) -> str:
        """Convert 07XXXXXXXX → +2547XXXXXXXX, leave +254... unchanged."""
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith("07") or phone.startswith("01"):
            return "+254" + phone[1:]
        if phone.startswith("254") and not phone.startswith("+"):
            return "+" + phone
        return phone


# ── 2. Dashboard alert (WebSocket event bus) ──────────────────────────────

# Module-level event bus — the WebSocket manager subscribes to this.
# Events are plain dicts: {"type": "ALERT", "staff_id": "...", "message": "..."}
_dashboard_subscribers: list = []


def subscribe_dashboard(callback) -> None:
    """Called by the WebSocket manager on connection."""
    _dashboard_subscribers.append(callback)


def unsubscribe_dashboard(callback) -> None:
    if callback in _dashboard_subscribers:
        _dashboard_subscribers.remove(callback)


class DashboardChannel(BaseChannel):
    """
    Pushes an alert event to all connected WebSocket clients.
    'recipient' here is a staff_id (UUID string) — the WS manager
    filters delivery to the right connection.

    If nobody is connected, the event is dropped (non-critical —
    the countdown timer cascade is the safety net).
    """
    name = "DASHBOARD"

    async def send(self, recipient: str, message: str, **kwargs) -> ChannelResult:
        event = {
            "type":     "STAFF_ALERT",
            "staff_id": recipient,
            "message":  message,
            "data":     kwargs,
        }
        delivered = 0
        for callback in list(_dashboard_subscribers):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
                delivered += 1
            except Exception as exc:
                logger.warning("Dashboard callback error: %s", exc)

        success = delivered > 0
        logger.info("Dashboard alert to %s — %d subscriber(s) reached.", recipient, delivered)
        return ChannelResult(
            channel="DASHBOARD", success=success,
            recipient=recipient, message=message,
            error=None if success else "No active WebSocket subscribers",
            metadata={"subscribers_reached": delivered},
        )


# ── 3. PA system ──────────────────────────────────────────────────────────

class PaChannel(BaseChannel):
    """
    Sends a text-to-speech announcement to a PA controller device.

    Most hospital PA systems accept announcements via:
      (a) A dedicated hardware controller with a simple HTTP or serial API.
      (b) A Windows PC running PA software that accepts HTTP POST requests.
      (c) A Raspberry Pi running espeak or a cloud TTS → audio output.

    This channel sends an HTTP POST to PA_CONTROLLER_URL (set in .env).
    The body is plain JSON: {"text": "Token OPD-004, please proceed to Room 3."}

    If your PA system uses a different protocol, override _post_to_pa().

    'recipient' here is the ward/zone identifier (e.g. "OPD_WAITING").
    'message'  is the text to be spoken verbatim.
    """
    name = "PA"

    def __init__(self):
        self.controller_url = getattr(settings, "PA_CONTROLLER_URL", "")

    async def send(self, recipient: str, message: str, **kwargs) -> ChannelResult:
        if not self.controller_url:
            logger.info("PA: PA_CONTROLLER_URL not set — skipping announcement.")
            return ChannelResult(
                channel="PA", success=False,
                recipient=recipient, message=message,
                error="PA_CONTROLLER_URL not configured",
            )

        try:
            await self._post_to_pa(zone=recipient, text=message)
            logger.info("PA announcement sent to zone %s: %s", recipient, message)
            return ChannelResult(
                channel="PA", success=True,
                recipient=recipient, message=message,
            )
        except Exception as exc:
            logger.error("PA error for zone %s: %s", recipient, exc)
            return ChannelResult(
                channel="PA", success=False,
                recipient=recipient, message=message,
                error=str(exc),
            )

    async def _post_to_pa(self, zone: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                self.controller_url,
                json={"zone": zone, "text": text, "priority": "normal"},
            )
            resp.raise_for_status()


# ── 4. Display board ──────────────────────────────────────────────────────

class DisplayBoardChannel(BaseChannel):
    """
    Broadcasts a queue-update event to all display board WebSocket clients.

    'recipient' is the dept_id — display boards subscribe per department.
    The actual queue data is NOT embedded in the event; the board's
    WebSocket handler will call GET /queues/{dept_id}/tokens to refresh.
    This keeps the event small and avoids data staleness issues.
    """
    name = "DISPLAY_BOARD"

    async def send(self, recipient: str, message: str, **kwargs) -> ChannelResult:
        event = {
            "type":    "QUEUE_UPDATE",
            "dept_id": recipient,
            "message": message,
        }
        delivered = 0
        for callback in list(_dashboard_subscribers):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
                delivered += 1
            except Exception as exc:
                logger.warning("Display board callback error: %s", exc)

        logger.info("Display board event for dept %s — %d subscriber(s).", recipient, delivered)
        return ChannelResult(
            channel="DISPLAY_BOARD", success=delivered > 0,
            recipient=recipient, message=message,
            metadata={"subscribers_reached": delivered},
        )
