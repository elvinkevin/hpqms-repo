**Phase 1A — Public Display Architecture & State Machine**.


# HPQMS Public Display Architecture — Phase 1A Summary

## 1. Core Architectural Paradigm

```
                          HPQMS BACKEND
                                │
               ┌────────────────┴────────────────┐
               │                                 │
        DisplaySnapshot                   NotificationEvent
    (Current State Projection)          (Lifecycle Transition)
               │                                 │
               └────────────────┬────────────────┘
                                ▼
                       DISPLAY STATE STORE
                  (Frontend Presentation Layer)
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
      BOARD MODE            ALERT MODE          CRITICAL MODE
   (Default/Rotation)    (7s Call Overlay)   (15s Priority Override)
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
                        HARDWARE PROFILE
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
   Door Signage         Standard Single-Screen       Large Atrium
  (10–15" Room)            (32–55" Board)           (65"+ Multi-Zone)
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                        HTML/CSS RENDERER

```

### Key Principles

* **State vs. Event Separation:** The backend emits domain projections (`DisplaySnapshot`) and lifecycle signals (`NotificationEvent`). Domain state (`QueueEntryStatus.CALLED`) is completely decoupled from UI presentation state (`DISPLAY_MODE = "ALERT"`).
* **Backend Source of Truth:** The display client acts strictly as a notification consumer. It renders projections and manages local transitions without mutating domain logic or deciding queue authority.
* **Information Density First:** Displays show actively relevant data—primarily answer **"Who is currently being served, and where should they go?"** rather than listing empty or inactive department rows.

---

## 2. Display State Machine & Behavioral Matrix

### 2.1 The Three Presentation Modes

| Mode | Trigger Event | Duration | Visual Treatment | Audio Treatment |
| --- | --- | --- | --- | --- |
| **ALERT MODE** | Incoming `TOKEN_CALLED` | **7 seconds** (configurable) | Full-screen or high-prominence overlay; large token number + target counter | Standard call chime |
| **BOARD MODE** | Default state / Alert timeout | Continuous | Structured table of active calls; page rotation for single-screen | None |
| **CRITICAL MODE** | `CRITICAL` priority event | **15 seconds** (or explicit clear) | High-contrast emergency modal; pauses active alert queue | Double-tone urgent chime |

---

### 2.2 Alert Processing & Queue Dynamics

```
                            Normal Call
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │  Push to Alert Queue  │
                     │   (FIFO, Max Depth 5) │
                     └───────────┬───────────┘
                                 │
                   CRITICAL Event Arrives?
                                 │
                 ┌───────────────┴───────────────┐
                YES                              NO
                 │                               │
                 ▼                               ▼
     ┌───────────────────────┐       ┌───────────────────────┐
     │ PAUSE Normal Queue    │       │ Process 7s Alert      │
     │ Display CRITICAL (15s)│       │ Overlay + Chime       │
     │ RESUME Normal Queue   │       └───────────┬───────────┘
     └───────────────────────┘                   │
                                                 ▼
                                     ┌───────────────────────┐
                                     │ Move to BOARD MODE    │
                                     │ (Static Highlight)    │
                                     └───────────────────────┘

```

* **Pause-and-Resume Queueing:** Incoming `CRITICAL` events temporarily pause normal alert processing. Once cleared, the queue resumes without losing pending call notifications.
* **Queue Overflow Safety:** If the alert queue exceeds its maximum depth ($N=5$), older non-critical alerts update directly on the background Service Board to ensure no call display drift occurs during morning rushes.
* **Static Post-Alert Highlighting:** The 7-second pulsating alert is restricted to Alert Mode. When returning to Board Mode, tokens in `CALLED` status render as **static highlighted rows** (accent border/elevated background), transitioning to standard styling once `IN_PROGRESS`.

---

## 3. Single-Screen Multi-Department Engine

For hospitals running multiple departments on a single 32–55" display:

```
    PAGE 1 (Active Depts 1–4)
   ┌─────────────────────────┐
   │ RECEPTION         A-028 │
   │ PHARMACY          P-014 │
   │ LABORATORY        L-009 │
   │ CONSULTATION      C-031 │
   └────────────┬────────────┘
                │ 10-Second Rotation
                ▼
    PAGE 2 (Active Depts 5–8)
   ┌─────────────────────────┐
   │ RADIOLOGY         R-014 │
   │ CASHIER           C-019 │
   │ DENTAL            D-004 │
   │ TRIAGE            T-011 │
   └─────────────────────────┘

```

### Smart Page Jump Engine

If `R-014` is called for Radiology while Page 1 is active:

1. **ALERT MODE:** Screen triggers the 7-second alert overlay (`R-014` $\rightarrow$ Radiology Counter 2).
2. **SMART JUMP:** Alert dismisses $\rightarrow$ Display immediately jumps to **Page 2** (where Radiology resides).
3. **PAGE HOLD:** Page 2 is held for an additional **15 seconds** before normal 10-second auto-rotation resumes.

---

## 4. Operational & Idle States

| Operational Condition | Public Board State | UI Behavior |
| --- | --- | --- |
| **Active Service** | `NOW SERVING` | Displays active `CALLED` and `IN_PROGRESS` tokens. |
| **Department Idle** | Status Badge: `NO ACTIVE CALLS` or `OPEN` | Counter is operational; no token actively being served. |
| **System-Wide Idle (0–5 min)** | Standby Card | Branded message: *"All services are open. Please take a token and await your call."* |
| **System-Wide Idle (> 5 min)** | Ambient Mode | Rotating announcements/health info with burn-in protection; wakes instantly on next call event. |

---

## 5. Phase 1A Agreement Checklist

* [x] **Board Mode** — Default state rendering active serving tokens.
* [x] **Alert Mode** — 7-second focused overlay with audio chime for calls.
* [x] **Critical Mode** — 15-second pause-and-resume override for high-priority alerts.
* [x] **Token Visual Lifecycle** — Alert pulse $\rightarrow$ Static `CALLED` highlight $\rightarrow$ Standard `IN_PROGRESS` $\rightarrow$ Optional recent ticker.
* [x] **Smart Rotation Engine** — Auto-pagination with immediate jump-to-page on hidden department calls.
* [x] **Activity-Driven Density** — Only departments with active calls occupy board space on compact/standard screens.
* [x] **Presentation-Agnostic Backend** — Hardware profile layouts fully managed on the frontend.
* [x] **Dual Idle System** — Branded standby card transitioning to ambient protection mode.


Phase 1B Summary — Visual Wireframes & Layout Specification (Refined)
1. Core Visual Principles & Hierarchy
Data-to-Visual Decoupling: The backend emits domain projections (DisplaySnapshot); the frontend determines visual layout density and pagination based on the active Layout Strategy.

Primary Information Hierarchy: Every strategy prioritizes three critical data points above all else:

TOKEN (Largest typography, highest contrast)

DESTINATION / DEPARTMENT

SERVICE POINT (Generic, configurable term e.g., "Room 3", "Window 5", "Counter 1", "Desk A")

Active-Only Board Rendering: To eliminate wasted screen real estate, multi-department displays render only departments with active calls (CALLED or IN_PROGRESS). Idle departments with zero active calls are filtered out automatically.

2. Visual State Hierarchy
┌────────────────────────────────────────────────────────────────────────┐
│  STATE        │ VISUAL TREATMENT                                       │
├───────────────┼────────────────────────────────────────────────────────┤
│  ALERT MODE   │ 7s full-screen / centered overlay; blurred backdrop;   │
│               │ solid high-contrast card; pulsating focus.             │
├───────────────┼────────────────────────────────────────────────────────┤
│  CALLED       │ Static board row highlight; solid primary accent       │
│               │ border; "JUST CALLED" badge; tabular figures.          │
├───────────────┼────────────────────────────────────────────────────────┤
│  IN_PROGRESS  │ Standard board row styling; clean, legible typography; │
│               │ assigned service point clearly displayed.              │
├───────────────┼────────────────────────────────────────────────────────┤
│  STANDBY /    │ Triggered when 0 active calls remain system-wide;      │
│  AMBIENT      │ branded message card, transitioning after 5 minutes to │
│               │ rotating health announcements + screen saver.          │
└───────────────┴────────────────────────────────────────────────────────┘



Here is the formal locking and consolidation of **Phase 1C — Display Configuration Model**.

Separating **Role** (purpose), **Physical Profile** (hardware capability), **Layout Strategy** (data arrangement), and **Department Filters** (scoped authority) solves the digital signage matrix cleanly. One frontend client codebase can now power a 10" tablet outside Consultation Room 3, a 32" Pharmacy waiting area screen, a 55" rotating main board, or a multi-zone 75" lobby video wall simply by swapping out the JSON configuration object.

---

# Phase 1C Summary & Decision Record — Display Configuration Model

## 1. Architectural Taxonomy

To avoid coupling hardware size to display intent, Phase 1C locks four distinct configuration dimensions:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DISPLAY IDENTITY                                 │
│                   display_id  |  display_name                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       ▼                               ▼                               ▼
┌──────────────┐               ┌──────────────┐               ┌──────────────┐
│ DISPLAY ROLE │               │   PHYSICAL   │               │    LAYOUT    │
│ (What is it  │               │   PROFILE    │               │   STRATEGY   │
│   intended   │               │ (Hardware /  │               │  (How is data│
│   to do?)    │               │  Density)    │               │ arranged?)   │
├──────────────┤               ├──────────────┤               ├──────────────┤
│ MAIN_LOBBY   │               │ DOOR         │               │ ROOM         │
│ DEPARTMENT   │               │ COMPACT      │               │ SINGLE_DEPT  │
│ ROOM         │               │ STANDARD     │               │ ROTATING_    │
│ EMERGENCY    │               │ LARGE        │               │   BOARD      │
│ RECEPTION    │               └──────────────┘               │ ATRIUM       │
│ CUSTOM       │                                              └──────────────┘
└──────────────┘

```

* **Role:** Semantic intent (*Where is this screen placed and why?*).
* **Physical Profile:** Hardware capability (*What screen size and spatial density are we designing for?*).
* **Layout Strategy:** Information arrangement (*How does the renderer map snapshots to DOM components?*).
* **Department Filter:** Data scope (*Which subset of hospital events does this screen consume?*).

---

## 2. Canonical Configuration Schema (`js/config.js`)

Below is the production contract for client-side configurations. Initially, this resides in `js/config.js` on the client. When backend display-management endpoints are introduced in later phases, the client can fetch this exact JSON schema over HTTP/REST at boot time without requiring any changes to the frontend state machine or rendering pipeline.

```javascript
// frontend/public-display/js/config.js

export const DISPLAY_CONFIG = {
  // 1. Identity
  display_id: "main-lobby-tv-01",
  display_name: "Main Lobby Central Display",

  // 2. Semantic Role & Physical Hardware
  role: "MAIN_LOBBY",         // "MAIN_LOBBY" | "DEPARTMENT" | "ROOM" | "EMERGENCY" | "RECEPTION" | "CUSTOM"
  profile: "STANDARD",        // "DOOR" | "COMPACT" | "STANDARD" | "LARGE"
  layout: "ROTATING_BOARD",   // "ROOM" | "SINGLE_DEPARTMENT" | "ROTATING_BOARD" | "ATRIUM"

  // 3. Department & Service Point Scoping
  // Empty array [] = Unfiltered / All Departments
  department_ids: [],
  service_point_ids: [],      // e.g. ["ROOM_03"] for DOOR role

  // 4. Pagination & Rotation Engine
  rotation: {
    enabled: true,
    departments_per_page: 4,
    interval_ms: 10000,       // 10-second standard rotation
    smart_hold_ms: 15000,      // 15-second hold on target page when jumping to a called token
  },

  // 5. Feature Flags & Visual Modules
  features: {
    show_clock: true,
    show_logo: true,
    show_announcements: true,
    show_recently_completed: false,
    show_waiting_count: false,
    show_estimated_wait: false,
  },

  // 6. Facility Branding & White-Label Layer
  branding: {
    show_logo: true,
    facility_name: "Aga Khan University Hospital",
    logo_url: "/assets/brand/logo.svg",
    default_service_point_label: "Counter", // Fallback label ("Counter", "Room", "Window", "Desk")
  },

  // 7. Alert & State Machine Parameters
  alerts: {
    enabled: true,
    duration_ms: 7000,          // 7-second call overlay
    critical_duration_ms: 15000,// 15-second emergency override
    max_queue_depth: 5,
    enable_chime: true,
  },

  // 8. Standby & Idle Power Engine
  idle: {
    enabled: true,
    standby_after_ms: 300000,   // 5 minutes of 0 calls -> Standby Screen
    ambient_after_ms: 600000,   // 10 minutes of 0 calls -> Ambient / Protection Mode
  },

  // 9. Gateway Connection Parameters
  network: {
    ws_url: "ws://localhost:8000/ws/display",
    snapshot_url: "/api/v1/display/snapshot",
    reconnect_interval_ms: 3000,
  }
};

```

---

## 3. Deployment Matrix Verification

This schema handles all common deployment scenarios cleanly without modifying a single line of backend or rendering code:

| Deployment Scenario | Role | Profile | Layout | Filters | Primary Behavior |
| --- | --- | --- | --- | --- | --- |
| **Single-TV Clinic** | `MAIN_LOBBY` | `STANDARD` | `ROTATING_BOARD` | `[]` | Active-only multi-department table; 10s auto-rotation; 15s smart jump to target page on incoming call. |
| **Pharmacy Waiting Room** | `DEPARTMENT` | `COMPACT` | `SINGLE_DEPARTMENT` | `["DEPT_PHARMACY"]` | Filtered exclusively to Pharmacy; shows active Desks/Counters 1–4; no rotation required. |
| **Consultation Door** | `ROOM` | `DOOR` | `ROOM` | `["DEPT_CONSULT"]` + `service_point: "ROOM_03"` | Single room display; prominent `CALLED` / `IN_PROGRESS` token focus; shows next pending token. |
| **Regional Referral Lobby** | `MAIN_LOBBY` | `LARGE` | `ATRIUM` | `[]` | Split-screen multi-zone grid; simultaneous active department columns; announcements & news marquee. |

---

## 4. Phase 1 Completion Status & Transition

With **Phase 1A** (State Machine), **Phase 1B** (Visual Layout Specifications & Wireframes), and **Phase 1C** (Configuration Schema) fully locked, our specification layer is complete.

```text
  Phase 1A: State Machine & Event Lifecycle           ✅ LOCKED
  Phase 1B: Visual Layout Specs & Wireframes          ✅ LOCKED
  Phase 1C: Display Configuration Schema              ✅ LOCKED
  ─────────────────────────────────────────────────────────────
  Phase 2: HTML Component Shell & DOM Hierarchy        ◀ NEXT STEP
  Phase 3: CSS System & Layout Strategy Engine
  Phase 4: JavaScript Modules & WS Connectivity

