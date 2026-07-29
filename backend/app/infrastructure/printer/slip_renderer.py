"""
slip_renderer.py

Generates the content of a queue token slip in two formats:

1. ESC/POS byte commands  — sent directly to a thermal receipt printer
   via a raw TCP socket on port 9100 (the standard RAW printing port).

2. HTML string  — returned to the frontend so the browser's print dialog
   can be used as a fallback when no network printer is reachable.

ESC/POS is the de-facto standard for thermal printers (Epson, Xprinter,
GOOJPRT, etc.). All commands used here are from the base ESC/POS spec
and work on every printer that claims ESC/POS compatibility.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# ── ESC/POS command constants ─────────────────────────────────────────────

ESC  = b"\x1b"
GS   = b"\x1d"

INIT          = ESC + b"@"          # initialise printer (reset)
ALIGN_LEFT    = ESC + b"a\x00"
ALIGN_CENTER  = ESC + b"a\x01"
ALIGN_RIGHT   = ESC + b"a\x02"
BOLD_ON       = ESC + b"E\x01"
BOLD_OFF      = ESC + b"E\x00"
DOUBLE_HEIGHT = GS  + b"!\x10"     # double height only
DOUBLE_BOTH   = GS  + b"!\x11"     # double height + width
NORMAL_SIZE   = GS  + b"!\x00"
UNDERLINE_ON  = ESC + b"-\x01"
UNDERLINE_OFF = ESC + b"-\x00"
FEED_1        = ESC + b"d\x01"     # feed 1 line
FEED_3        = ESC + b"d\x03"
FULL_CUT      = GS  + b"V\x00"     # full paper cut


def _line(text: str, encoding: str = "utf-8") -> bytes:
    """Encode a text line and append a newline."""
    return text.encode(encoding) + b"\n"


def _divider(char: str = "-", width: int = 32) -> bytes:
    return _line(char * width)


# ── Slip data ─────────────────────────────────────────────────────────────

@dataclass
class SlipData:
    token_number:    str          # e.g. "OPD-004"
    patient_name:    str          # e.g. "James Odhiambo"
    department:      str          # e.g. "General OPD"
    issued_at:       datetime
    estimated_wait:  int          # minutes
    hospital_name:   str = "HPQMS Hospital"
    triage_level:    str = "NON_URGENT"
    queue_position:  Optional[int] = None


# ── ESC/POS renderer ──────────────────────────────────────────────────────

def render_escpos(slip: SlipData) -> bytes:
    """
    Returns raw ESC/POS bytes ready to be written to a TCP socket on port 9100.

    Slip layout (32-char width):
    ┌────────────────────────────────┐
    │       HPQMS Hospital           │  ← bold, centered
    │   OUTPATIENT QUEUE TICKET      │  ← centered
    │ ────────────────────────────── │
    │        OPD-004                 │  ← double size, centered
    │ ────────────────────────────── │
    │ Patient  : James Odhiambo      │
    │ Dept     : General OPD         │
    │ Priority : NON_URGENT          │
    │ Position : 4 in queue          │
    │ Issued   : 08:15  15 Jul 2026  │
    │ Est. wait: ~22 minutes         │
    │ ────────────────────────────── │
    │  Please keep this slip and     │
    │  watch the display board.      │
    │  You will also receive an SMS. │
    └────────────────────────────────┘
    """
    issued_str  = slip.issued_at.strftime("%H:%M  %d %b %Y")
    position_str = f"{slip.queue_position} in queue" if slip.queue_position else "—"
    priority_display = slip.triage_level.replace("_", " ")

    buf = bytearray()

    # Initialise
    buf += INIT

    # ── Header ──────────────────────────────────────────────────────────
    buf += ALIGN_CENTER
    buf += BOLD_ON
    buf += _line(slip.hospital_name.upper())
    buf += BOLD_OFF
    buf += _line("OUTPATIENT QUEUE TICKET")
    buf += _divider()

    # ── Token number — large ────────────────────────────────────────────
    buf += DOUBLE_BOTH
    buf += BOLD_ON
    buf += _line(f"  {slip.token_number}  ")
    buf += NORMAL_SIZE
    buf += BOLD_OFF
    buf += _divider()

    # ── Patient details ─────────────────────────────────────────────────
    buf += ALIGN_LEFT
    buf += _line(f"Patient  : {slip.patient_name}")
    buf += _line(f"Dept     : {slip.department}")
    buf += _line(f"Priority : {priority_display}")
    buf += _line(f"Position : {position_str}")
    buf += _line(f"Issued   : {issued_str}")

    # Highlight wait time
    buf += BOLD_ON
    buf += _line(f"Est. wait: ~{slip.estimated_wait} minutes")
    buf += BOLD_OFF

    buf += _divider()

    # ── Footer ──────────────────────────────────────────────────────────
    buf += ALIGN_CENTER
    buf += _line("Please keep this slip and")
    buf += _line("watch the display board.")
    buf += _line("You will also receive an SMS.")
    buf += FEED_3
    buf += FULL_CUT

    return bytes(buf)


def render_text(slip: SlipData) -> str:
    """Render a plain-text slip for Windows spooler printing."""
    issued_str = slip.issued_at.strftime("%H:%M  %d %b %Y")
    position_str = f"{slip.queue_position} in queue" if slip.queue_position else "—"
    priority_display = slip.triage_level.replace("_", " ")

    lines = [
        slip.hospital_name.upper(),
        "OUTPATIENT QUEUE TICKET",
        "" + "-" * 32,
        f"Token     : {slip.token_number}",
        "" + "-" * 32,
        f"Patient   : {slip.patient_name}",
        f"Department: {slip.department}",
        f"Priority  : {priority_display}",
        f"Position  : {position_str}",
        f"Issued    : {issued_str}",
        "" + "-" * 32,
        f"Estimated wait: ~{slip.estimated_wait} minutes",
        "" + "-" * 32,
        "Please keep this slip and watch the display board.",
        "You will also receive an SMS update.",
    ]

    return "\r\n".join(lines) + "\r\n"


# ── HTML renderer (browser print fallback) ────────────────────────────────

def render_html(slip: SlipData) -> str:
    """
    Returns a self-contained HTML string the frontend can open in a
    new tab and trigger window.print() on. Styled for 80mm thermal paper.
    """
    issued_str   = slip.issued_at.strftime("%H:%M  •  %d %b %Y")
    position_str = f"{slip.queue_position} in queue" if slip.queue_position else "—"
    priority_display = slip.triage_level.replace("_", " ")

    priority_color = {
        "CRITICAL":    "#c0392b",
        "URGENT":      "#e67e22",
        "SEMI_URGENT": "#f1c40f",
        "NON_URGENT":  "#27ae60",
    }.get(slip.triage_level, "#27ae60")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Queue Token {slip.token_number}</title>
<style>
  @page {{ size: 80mm auto; margin: 4mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Courier New', monospace;
    font-size: 12px;
    width: 72mm;
    color: #000;
  }}
  .center  {{ text-align: center; }}
  .divider {{ border-top: 1px dashed #000; margin: 6px 0; }}
  .hospital {{ font-size: 13px; font-weight: bold; letter-spacing: 1px; }}
  .subtitle {{ font-size: 11px; }}
  .token-num {{
    font-size: 32px;
    font-weight: bold;
    letter-spacing: 4px;
    padding: 6px 0;
  }}
  .row {{ display: flex; justify-content: space-between; padding: 2px 0; }}
  .label {{ color: #555; }}
  .priority-badge {{
    display: inline-block;
    padding: 1px 8px;
    border-radius: 3px;
    background: {priority_color};
    color: white;
    font-weight: bold;
    font-size: 11px;
  }}
  .wait {{ font-size: 14px; font-weight: bold; text-align: center; padding: 4px 0; }}
  .footer {{ font-size: 10px; text-align: center; color: #333; margin-top: 4px; }}
  @media print {{ button {{ display: none; }} }}
</style>
</head>
<body>
<div class="center">
  <div class="hospital">{slip.hospital_name.upper()}</div>
  <div class="subtitle">OUTPATIENT QUEUE TICKET</div>
</div>

<div class="divider"></div>

<div class="center token-num">{slip.token_number}</div>

<div class="divider"></div>

<div class="row"><span class="label">Patient</span><span>{slip.patient_name}</span></div>
<div class="row"><span class="label">Department</span><span>{slip.department}</span></div>
<div class="row">
  <span class="label">Priority</span>
  <span class="priority-badge">{priority_display}</span>
</div>
<div class="row"><span class="label">Position</span><span>{position_str}</span></div>
<div class="row"><span class="label">Issued</span><span>{issued_str}</span></div>

<div class="divider"></div>

<div class="wait">Estimated wait: ~{slip.estimated_wait} min</div>

<div class="divider"></div>

<div class="footer">
  Keep this slip &amp; watch the display board.<br>
  You will also receive an SMS update.
</div>

<br>
<div class="center">
  <button onclick="window.print()">Print Slip</button>
</div>
</body>
</html>"""
