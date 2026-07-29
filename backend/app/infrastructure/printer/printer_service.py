"""
printer_service.py

Sends a token slip to a thermal printer via raw TCP (port 9100).
Falls back gracefully to HTML if no printer is reachable.

How thermal printer networking works:
  Most networked thermal printers (Epson TM series, Xprinter, etc.) expose
  a raw TCP socket on port 9100. You open a socket, write the ESC/POS bytes,
  and close it. No HTTP, no driver, no spooler needed.

  USB printers:  connect via /dev/usb/lp0 on Linux or a shared network
                 print server (e.g. CUPS) that exposes the same port 9100.

  Local network: plug the printer into the hospital LAN. Configure a static
                 IP (e.g. 192.168.1.200) via the printer's settings menu.
                 Set PRINTER_HOST and PRINTER_PORT in .env accordingly.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.infrastructure.printer.slip_renderer import SlipData, render_escpos, render_html, render_text

try:
    import win32print
except ImportError:
    win32print = None

logger = logging.getLogger(__name__)


class PrinterService:

    def __init__(
        self,
        host: str = "",
        port: int = 9100,
        timeout: float = 5.0,
    ):
        self.host    = host or getattr(settings, "PRINTER_HOST", "")
        self.port    = port or getattr(settings, "PRINTER_PORT", 9100)
        self.timeout = timeout

    # ── Public API ────────────────────────────────────────────────────────

    async def print_token_slip(self, slip: SlipData) -> dict:
        """
        Attempt to print a slip to the network thermal printer.
        Returns a result dict with channel, success flag, and HTML fallback.

        Always returns HTML regardless of print outcome so the frontend
        can open a print preview tab as a secondary output.
        """
        html = render_html(slip)
        result = {
            "token_number": slip.token_number,
            "html":         html,            # always returned
            "printed":      False,
            "channel":      "html_fallback",
            "error":        None,
        }

        if settings.USE_WINDOWS_SPOOLER and win32print is not None:
            try:
                await self._print_to_windows_spooler(slip)
                result["printed"] = True
                result["channel"] = "windows_spooler"
                logger.info("Slip %s printed via Windows spooler", slip.token_number)
                return result
            except Exception as exc:
                result["error"] = f"Windows spooler failed: {exc}"
                result["channel"] = "windows_spooler_failed"
                logger.warning(
                    "Windows spooler failed for slip %s — falling back to raw TCP/HTML. Error: %s",
                    slip.token_number,
                    exc,
                )

        if not self.host:
            logger.info(
                "No PRINTER_HOST configured — slip for %s returned as HTML only.",
                slip.token_number,
            )
            return result

        try:
            await asyncio.wait_for(
                self._send_to_printer(render_escpos(slip)),
                timeout=self.timeout,
            )
            result["printed"] = True
            result["channel"] = f"tcp://{self.host}:{self.port}"
            logger.info("Slip %s printed to %s:%s", slip.token_number, self.host, self.port)

        except asyncio.TimeoutError:
            result["error"] = f"Printer at {self.host}:{self.port} timed out after {self.timeout}s"
            logger.warning("Printer timeout for slip %s — HTML fallback served.", slip.token_number)

        except OSError as exc:
            result["error"] = f"Printer connection failed: {exc}"
            logger.warning("Printer unreachable for slip %s — HTML fallback served. Error: %s",
                           slip.token_number, exc)

        return result

    # ── Internal ──────────────────────────────────────────────────────────

    async def _send_to_printer(self, data: bytes) -> None:
        """Open a raw TCP connection, write all bytes, close cleanly."""
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(data)
            await writer.drain()
        finally:            
            writer.close()
            await writer.wait_closed()

    async def _print_to_windows_spooler(self, slip: SlipData) -> None:
        """Send the slip text to the Windows print spooler using the selected printer."""
        if win32print is None:
            raise RuntimeError("pywin32 is not installed")

        printer_name = settings.WINDOWS_PRINTER_NAME or win32print.GetDefaultPrinter()
        if not printer_name:
            raise RuntimeError("No Windows printer configured or available")

        data = render_text(slip).encode("utf-8")

        def spooler_job():
            handle = win32print.OpenPrinter(printer_name)
            try:
                doc_info = ("HPQMS Queue Slip", None, "RAW")
                job = win32print.StartDocPrinter(handle, 1, doc_info)
                try:
                    win32print.StartPagePrinter(handle)
                    win32print.WritePrinter(handle, data)
                    win32print.EndPagePrinter(handle)
                finally:
                    win32print.EndDocPrinter(handle)
            finally:
                win32print.ClosePrinter(handle)

        await asyncio.to_thread(spooler_job)

    async def ping(self) -> bool:
        """Check whether the printer is reachable. Used by the health endpoint."""
        if not self.host:
            return False
        try:
            await asyncio.wait_for(
                self._send_to_printer(b""),   # empty payload just tests connectivity
                timeout=2.0,
            )
            return True
        except Exception:
            return False


# ── Module-level singleton ────────────────────────────────────────────────
# Imported by the endpoint and by tests.
printer_service = PrinterService()
