# Administrator Setup & Operations Workflow

Step-by-step workflows for the hospital administrator setting up HPQMS for a
new deployment — **entirely through the Admin Dashboard UI** (no scripts, no
`seed.py`). `seed.py` remains a developer convenience only; in production the
admin performs all setup through the dashboard, and the backend validates
every action the same way regardless of who calls it.

Related docs: [`NAMING_CONVENTIONS.md`](./NAMING_CONVENTIONS.md) (ID and code
formats referenced below).

---

## Phase 0 — First login (bootstrap)

The first administrator is created at install time from environment
variables (this cannot be done through the UI, because there is no account to
log in with yet). Bootstrap also creates the starter service departments and
the separate `Administration` department:

1. DevOps sets `INITIAL_ADMIN_EMPLOYEE_ID` (e.g. `EMP-ADMIN01`) and
   `INITIAL_ADMIN_PASSWORD` (≥ 12 characters) in the deployment environment.
2. On startup, `bootstrap_admin.py` creates the starter service departments,
   a dedicated `Administration` department, and one ADMIN account. Existing
   admin accounts are attached to `Administration`; passwords are not reset.
3. The admin signs in with that employee ID and temporary password. The
   backend returns a short-lived setup-only token and does not issue normal
   session tokens.
4. The browser redirects to `admin-setup.html`. The admin sets their real
   first and last name and a new password (≥ 12 characters with uppercase,
   lowercase, number, and symbol). The setup token expires after 15 minutes.
5. After setup succeeds, the old password is replaced, the account is marked
   complete, and a new authenticated session opens the Admin dashboard.

> Everything after this point is done by the admin in the browser.

---

## Phase 1 — Create departments

**Where:** Admin Dashboard → **Departments** tab → ＋ Add department

Create one department per physical service area, in patient-flow order.
Recommended starter set (mirrors the seed conventions):

| Name                      | Code       | Type        | Max capacity |
| ------------------------- | ---------- | ----------- | ------------ |
| Reception Desk            | `REC`      | OPD         | 50           |
| Emergency Department      | `EMERGENCY`| EMERGENCY   | 30           |
| Triage & Vitals Station   | `TRIAGE`   | OPD         | 15           |
| General Consultation      | `CONSULT`  | OPD         | 25           |
| Administration            | `ADMIN`    | OPD         | 1            |

The `ADMIN` department is reserved for administrator accounts and is not a
patient service area. `DeptType` has no administrative value, so it uses the
existing general-purpose `OPD` type. Bootstrap adds this row automatically;
the admin does not need to create it.

Rules (enforced by the backend, see NAMING_CONVENTIONS.md §2):

- Code: 3–10 characters, starts with a letter, uppercase letters/digits only.
- The codes `RECEPTION`/`REC`, `EMERGENCY`, and `TRIAGE` are **routing
  aliases** — the kiosk routes walk-in / emergency / appointment entries by
  looking up these codes, so a deployment must keep those codes for those
  departments (display names can differ).
- Max capacity caps how many patients may queue in that department.

Ongoing management: Edit / Deactivate / Activate buttons per row.
Deactivating a department removes it from kiosk routing and new queue
assignments but preserves its history.

---

## Phase 2 — Create service points (stations)

**Where:** Admin Dashboard → **Departments** tab → right-hand "Service
points" panel → select a department → add stations.

Each department needs one station per staff member who will be seated at a
desk/window/room simultaneously. Guideline (based on the seed's model):

| Department | Stations                        | Type     |
| ---------- | ------------------------------- | -------- |
| `REC`      | `REC-C1`…`REC-C4` Counter 1–4, `REC-W1`–`W2` Window 1–2 | COUNTER / WINDOW |
| `TRIAGE`   | `TR-W1`…`TR-W4` Vitals Window 1–4 | WINDOW  |
| `CONSULT`  | `CO-R1`…`CO-R4` Consultation Room 1–4 | ROOM |
| `EMERGENCY`| `EM-DOOR1` Triage Door 1, `EM-R1` Resus Room 1 | DOOR / ROOM |

Fields per station:

- **Code** — short unique code within the department (recommended:
  `<DEPT-ABBREV>-<TYPE><N>`, e.g. `REC-C1`)
- **Label** — human-readable name shown to patients on displays
- **Station type** — COUNTER, ROOM, WINDOW, or DOOR

Each station can later be enabled/disabled (e.g. maintenance) via its
Enable/Disable button. Station codes are what staff bind to at shift start
(see §Phase 4).

---

## Phase 3 — Register staff members

**Where:** Admin Dashboard → **Staff** tab → ＋ Add staff

For each staff member create the account. Generate a secure temporary password
in the staff form (or enter one), then create the account. The success dialog
shows the employee ID and temporary password once and can copy both together.
The staff member must set a permanent password before opening any dashboard.

Fields:

- **Employee ID** — format `EMP-<DEPTCODE><sequence>`, e.g. `EMP-RECEP01`,
  `EMP-TRIAGE02`, `EMP-DOC-004`. This is also the staff member's **login ID**,
  so keep it short. Unique; backend rejects duplicates and malformed IDs.
- **First / Last name**
- **Role** — RECEPTIONIST, NURSE, TRIAGE_NURSE, DOCTOR, or ADMIN
- **Department** — the department the member belongs to (determines which
  stations they may bind to and which queues they serve)
- **Temporary password** — at least 8 characters. It is hidden in the form and
  shown only in the one-time success dialog; share it securely. Staff must set
  a permanent password (12+ characters, mixed case, number, and symbol) at
  first sign-in.

Suggested starter staffing (matching the seeded example hospital):

| Employee ID    | Role          | Department | Count |
| -------------- | ------------- | ---------- | ----- |
| `EMP-RECEP01…` | RECEPTIONIST  | REC        | 4–6   |
| `EMP-TRIAGE01…`| TRIAGE_NURSE  | TRIAGE     | 4     |
| `EMP-DOC01…`   | DOCTOR        | CONSULT    | 4     |

Ongoing staff management (all in the Staff tab):

- **Manage** — edit names/specialization, change role, transfer department.
  Transferring a member to another department automatically releases their
  old station binding.
- **Overflow menu (⋮)** — reset password; activate/deactivate account.
  Deactivating an account blocks login immediately (e.g. departure), but
  preserves the record and audit history.
- **Search** — filter the directory by name, employee ID, department, or role.

Every role change, transfer, and password reset is recorded in the **Audit
trail** tab.

---

## Phase 4 — Daily staff workflow (after setup)

Once staff accounts exist, each staff member's routine is:

1. **Log in** with their employee ID and password (staff login page).
2. **Check in (start shift)** — dashboard header toggle. This marks them on
   duty and they appear on the admin Overview's on-duty roster. Logging out
   also ends the shift.
3. **Bind to a station** — from their own dashboard, bind to a service point
   in their department (e.g. a receptionist binds to `REC-C2`). This is what
   routes called tokens to their desk on the public display.
4. **Serve the queue** — call next patient, start service, complete, or
   no-show tokens from their department view.
5. **Check out (end shift)** — header toggle again; optionally unbind the
   station. Logout ends the shift and releases the station automatically.

The admin sees all of this live: the Overview tab shows per-department queue
counts and the on-duty roster, updating in real time via WebSocket.

---

## Password reset workflows

### A. Staff member still knows their password (self-service)

Staff login page / their dashboard → change password, supplying the current
password. No admin involvement. (`POST /api/auth/change-password`.)

### B. Staff member is locked out (admin-initiated recovery)

1. Admin opens **Staff**, locates the member, and selects the reset icon beside
   their name.
2. After confirmation, the system invalidates the current password and issues a
   one-time recovery code. The code is shown once and can be copied from the
   confirmation dialog.
3. Share the recovery code directly and securely. It expires after 15 minutes.
4. The member enters their employee ID and recovery code on the staff sign-in
   page. The code is consumed at successful sign-in, which opens only the
   restricted password setup page.
5. The member sets a new personal password before they receive normal system
   access. Resetting the account ends active access, marks the member off duty,
   and releases their assigned station. The action is recorded in the audit
   trail.
### C. Admin lost their own password

No other admin → the only recovery is a privileged bootstrap: set the
`INITIAL_ADMIN_*` environment variables and re-run the admin bootstrap step —
it never touches an existing admin account, so DevOps must temporarily
deactivate/reset the lost account at the database level following the
deployment runbook. Keep at least two active ADMIN accounts per deployment to
avoid this situation.

---

## Other admin workflows

### Department overview drill-down
Overview tab → click a department name → live detail card (waiting, called,
in service, urgent, staff on duty) for that department only.

### Audit trail
Audit trail tab → filter by action (`ROLE_CHANGED`, `PASSWORD_RESET`,
`DEPARTMENT_TRANSFER`, …), staff ID, or entity → view who did what and when.
Showing up to 50 records per query.

### Kiosk entry routing (verification step after Phase 1–3)
Because routing is code-based, after setup the admin should verify the kiosk
routes correctly: a walk-in lands in the `REC`/`RECEPTION` queue, an
appointment in `TRIAGE`, an emergency in `EMERGENCY`. If routing returns
"department not found", the corresponding department is missing or renamed —
re-create/rename it back to the reserved code.

---

## Quick reference: what is enforced where

| Rule                              | Enforced by                                        |
| --------------------------------- | -------------------------------------------------- |
| Employee ID format + uniqueness   | Schema validator + DB unique constraint            |
| Department code format            | Schema validator (create & update)                 |
| Reserved routing codes            | Documentation (routing looks them up by code)      |
| Initial admin bootstrap           | Env vars + idempotent bootstrap (skips if admin exists) |
| Admin-only operations             | RBAC dependency on every admin route               |
| Password resets                   | Admin-only, audited (`PASSWORD_RESET`)             |
