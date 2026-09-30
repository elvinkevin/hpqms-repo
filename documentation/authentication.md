# HQMS Authentication Workflow

This document describes the complete staff authentication process: how sessions
are issued, the special first-login gates, password self-service, and the
admin-initiated password reset (recovery code) flow, including how the server
communicates with the frontend at each step.

All endpoints below are mounted under `/api/auth` unless stated otherwise
(`PATCH /api/staff/{staff_id}/reset-password` is on the staff router).

---

## 1. Token types

The server issues **four distinct JWT types**, each scoped to what it may be
used for (`backend/app/core/security.py`):

| Token | `type` claim | Lifetime | Usable for |
|---|---|---|---|
| Access token | `access` | Short-lived (default JWT expiry) | Any authenticated API call (`Authorization: Bearer ...`) |
| Refresh token | `refresh` | Longer-lived | Only `POST /api/auth/refresh` |
| Admin setup token | `admin_setup` | 15 minutes | Only `POST /api/auth/complete-admin-setup` |
| Password change token | `password_change` | 15 minutes | Only `POST /api/auth/complete-password-change` |

Both restricted tokens carry a `scope` claim in addition to `type`
(`scope=setup` / `scope=password_change`), and the decoders reject any token
whose `type`/`scope` pair does not match. A setup token can therefore never be
replayed as an access token or vice versa.

Access tokens carry the claims `sub` (staff UUID), `employee_id`, `role` and
`dept_id`; the refresh token carries only `sub`.

---

## 2. Session issuance — normal login

`POST /api/auth/login` with `{ "employee_id": "password": ... }`
(`LoginRequest` schema; no format validation on the ID here so legacy and
locked accounts can still attempt sign-in).

The service (`AuthService.login`) resolves the staff row **filtered on
`is_active = true`** with `SELECT ... FOR UPDATE` (row lock, preventing
concurrent logins racing the same account state), then walks a decision chain:

```
1. No active account found            -> 401 "Invalid employee ID or password."
2. Pending recovery code (§5)         -> password_change_token, no session
3. Password does not verify           -> 401 "Invalid employee ID or password."
4. ADMIN and admin_setup_complete=False -> setup_token, no session      (§3)
5. requires_password_change=True      -> password_change_token, no session (§4)
6. Otherwise                          -> full session (access + refresh)
```

On success the server also sets `is_on_duty = True` — a desktop workstation
sign-in starts the shift automatically — commits, and returns a `TokenResponse`:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "setup_required": false,
  "setup_token": null,
  "password_change_required": false,
  "password_change_token": null,
  "staff": { "staff_id": "...", "employee_id": "...", "first_name": "...", ... }
}
```

**Frontend contract:** a login response is a *full session* only when
`access_token` is non-null. If instead `setup_required` or
`password_change_required` is true, the frontend must route to the
corresponding setup screen and use the returned restricted token — it cannot
call any other API with it.

Login is rate-limited (`rate_limit_auth_dependency`); the client receives
`429` when it exceeds the budget.

### Session validation on every request

`get_current_user` (the dependency behind `/api/auth/me` and every protected
route) decodes the access token, loads the staff row, and re-checks account
state:

- staff missing or `is_active = false` → `401`
- admin with unfinished setup → `403` "Complete administrator setup before
  accessing the system."
- `requires_password_change` → `403` "Change the temporary password before
  accessing the system."

So a stolen access token stops working the moment the account is deactivated
or still sits behind a credential gate.

---

## 3. First-time administrator setup

Purpose: an admin account created via seeding/bootstrap starts with a
temporary password and `admin_setup_complete = false`. Before it can do
anything, the administrator must personalise the profile and replace the
temporary password.

### 3.1 Login attempt

The frontend POSTs normal credentials. The server returns:

```json
{ "setup_required": true, "setup_token": "eyJ...", "access_token": null,
  "refresh_token": null, "staff": { ... } }
```

**Frontend:** show the admin-setup form (first name, last name, new password).
Nothing else is callable — `/me` and `/refresh` both return `403` while the
gate is active.

### 3.2 Completing setup

`POST /api/auth/complete-admin-setup` with
`{ "setup_token", "first_name", "last_name", "new_password" }`.

Schema validation (`AdminSetupCompleteRequest`): password ≥ 12 chars, ≤ 72
UTF-8 bytes, must contain upper, lower, digit and symbol; names must be
non-blank. Failures surface as `422` before the service is reached.

Service rules, in order:

| Condition | Response |
|---|---|
| Token invalid / wrong type / bad UUID | `401` "Invalid administrator setup token." |
| Staff missing, inactive, or not role ADMIN | `401` "Administrator account is unavailable." |
| `admin_setup_complete` already true | `409` "Administrator setup has already been completed." |
| New password equals the temporary password | `400` "Choose a password different from the temporary password." |

On success the server sets `first_name`, `last_name`, the new hashed password,
`admin_setup_complete = true`, clears any pending password-change state, marks
the admin on duty, commits — and **immediately returns a full session**
(access + refresh tokens). The frontend stores both tokens and drops the
setup token.

---

## 4. Staff temporary password change (first login)

Newly provisioned staff (created through `POST /api/staff` or seeding) are
saved with `requires_password_change = true`. Their first login therefore
returns:

```json
{ "password_change_required": true, "password_change_token": "eyJ...",
  "access_token": null, "refresh_token": null, "staff": { ... } }
```

**Frontend:** show the "set your permanent password" screen and call
`POST /api/auth/complete-password-change` with
`{ "password_change_token", "new_password" }` (same password strength rules
and the same error ladder as admin setup: `401` bad token, `409` already
completed, `400` identical-to-temporary password, `422` weak password).

On success the server clears `requires_password_change` (and any recovery-code
state), starts the shift, and returns a **full session**. The temporary
password no longer works, and `/api/auth/refresh` plus all protected routes
are usable again. The change is single-use: replaying the same change token
afterwards returns `409`.

---

## 5. Admin-initiated password reset (recovery code)

Purpose: lockout recovery. An administrator can invalidate a staff member's
forgotten password without ever learning or choosing a new one.

### 5.1 Admin issues the reset

`PATCH /api/staff/{staff_id}/reset-password` (staff router, requires
`StaffRole.ADMIN` via `require_role`; other roles get `403`, anonymous `401`,
unknown staff `404`).

The server (`StaffService.reset_password`):

1. Replaces `hashed_password` with the hash of a **random unknown value**
   (`secrets.token_urlsafe(32)`), so the old password is dead immediately.
2. Generates a one-time recovery code `HPQMS-##########` (10 random digits).
3. Stores only a **bcrypt hash** of the code plus a
   `password_reset_code_expires_at = now + 15 minutes`.
4. Sets `requires_password_change = true`, ends any active shift
   (`is_on_duty = false`) and releases the station binding.
5. Writes a `PASSWORD_RESET` entry to the audit log and commits.

Response:

```json
{
  "message": "Password invalidated. Share the recovery code securely.",
  "recovery_code": "HPQMS-0427153891",
  "expires_in_minutes": 15
}
```

**Frontend:** the code is shown **once** to the admin, who must relay it to
the staff member out-of-band (phone/in person). It is not stored in plain text
anywhere.

### 5.2 Staff signs in with the recovery code

The staff member calls the ordinary `POST /api/auth/login`, but with the
recovery code in the `password` field. Because the row has
`requires_password_change` **and** a `password_reset_code_hash`, login
switches to recovery-code mode:

- code expired (`expires_at` missing/past) **or** does not verify →
  `401` "Invalid employee ID or recovery code."
- code valid → the code is **consumed** (hash and expiry nulled and committed)
  and the server returns `password_change_required: true` with a fresh
  `password_change_token`. No session tokens.

This makes the code single-use by construction; a second attempt returns
`401`.

### 5.3 Set the permanent password

Exactly the same handshake as §4:
`POST /api/auth/complete-password-change` → new full session. End-to-end:

```
Admin: PATCH /api/staff/{id}/reset-password ──► recovery_code (shown once)
Staff: POST /api/auth/login {code}           ──► password_change_token (code now dead)
Staff: POST /api/auth/complete-password-change ──► access + refresh tokens
Staff: POST /api/auth/login {new password}   ──► normal login works
```

---

## 6. Session maintenance

### Refresh

`POST /api/auth/refresh` with `{ "refresh_token": ... }` returns a new
`AccessTokenResponse` (`access_token` + `token_type`). The refresh token is
single-purpose: wrong type/expiry → `401`; staff since deactivated → `401`;
account still behind a setup or password-change gate → `403` with a message
telling the client to finish that flow first.

### Password self-service

`POST /api/auth/change-password` (`Bearer` access token required) with
`{ "current_password", "new_password" }` (min 8 chars, needs digit + upper).
Wrong current password → `400`. Note: this path does **not** clear
`requires_password_change` — accounts locked behind the first-login gate must
use the restricted-token flow in §3/§4.

### Logout

`POST /api/auth/logout` ends the shift server-side: sets `is_on_duty = false`
and releases `active_service_point_id`, and returns
`{ "message": "Logged out successfully." }`. Token revocation is client-side:
the frontend discards the stored tokens.

---

## 7. Status-code cheat sheet

| Code | Meaning |
|---|---|
| `200` | Success — check `setup_required` / `password_change_required` flags on login |
| `400` | Semantically valid request, refused (e.g. new password equals temporary) |
| `401` | Bad credentials, bad/expired/wrong-type token, inactive account |
| `403` | Authenticated but gated (setup pending / password change pending) or insufficient role |
| `404` | Unknown staff/resource |
| `409` | Conflict — gate already completed, duplicate employee ID |
| `422` | Schema validation failure (weak password, missing fields) |
| `429` | Auth rate limit exceeded |

---

## 8. Employee ID convention

IDs shown in the UI follow `EMP-<DEPTCODE><SEQUENCE>` (e.g. `EMP-TRIAGE01`,
`EMP-DOC-004`, legacy `EMP001`): literal `EMP` prefix, optional dash, 1–8
alphanumeric department mnemonic, optional dash, 2–4 digit sequence. The
validator normalises to uppercase. This is enforced on staff *creation*
schemas only — the login endpoint accepts whatever the account was stored
with.

---

## 9. Related tests

- `backend/tests/api/test_auth_api.py` — login/refresh/me/change-password/logout basics
- `backend/tests/api/test_auth_first_login_flows.py` — admin setup gate, temporary-password change, recovery-code journeys
- `backend/tests/api/test_staff_admin_actions.py` — admin reset endpoint, role/transfer actions, audit trail
- `backend/tests/unit/domain/services/test_auth_service.py` — service-layer login and change-password logic
