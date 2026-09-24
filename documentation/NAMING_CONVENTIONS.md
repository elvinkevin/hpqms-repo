# HPQMS Naming & Code Conventions

Operational conventions for identifiers that hospital administrators enter
manually when deploying or configuring the system. These are enforced by the
backend at the API schema layer, so invalid input is rejected at creation
time with a clear error message — no database migration is involved.

---

## 1. Employee IDs (`staff.employee_id`)

### Format

```
EMP-<DEPTCODE><sequence>
```

- Prefix: literal `EMP-`
- **DEPTCODE**: a short department mnemonic, 1–8 uppercase letters/digits
  (see §2 for the department code convention; the employee ID segment may be
  a shortened form of it)
- **Sequence**: 2–4 digits (`01`, `02`, … `1234`)
- An optional dash before the sequence is accepted: `EMP-LAB-001` ≡ `EMP-LAB001`
- Case-insensitive on input — the backend normalizes to uppercase, so
  `emp-triage02` and `EMP-TRIAGE02` are the same ID
- Validation regex: `EMP-[A-Z0-9]{1,8}-?\d{2,4}` (max length 20, unique)

### Examples

| Value          | Meaning                                  |
| -------------- | ---------------------------------------- |
| `EMP-RECEP01`  | 1st staff member seeded under Reception  |
| `EMP-TRIAGE02` | 2nd triage nurse                         |
| `EMP-DOC-001`  | 1st doctor (dash variant)                |
| `EMP-ADMIN01`  | Hospital administrator                   |

### Why this format

- `EMP` makes staff IDs instantly distinguishable from patient/visit numbers
- The department mnemonic keeps the ID self-describing in listings and audit
  trails even without a database join
- The sequence is the human part the administrator assigns; uniqueness is
  enforced by a DB unique constraint, so duplicates are rejected either way

### Notes

- Employees **log in with this ID** (`LoginRequest.employee_id`), so it
  appears on sign-in screens — keep it short and typable
- Existing seeded accounts (`EMP-RECEP01` … `EMP-DOC04`) already comply;
  no migration was needed
- Changing an employee's department later does **not** require changing
  their ID — the mnemonic reflects the department at hire time

---

## 2. Department codes (`departments.department_code`)

### Format

```
3–10 characters, starting with a letter,
uppercase letters and digits only
```

- Validation regex: `[A-Z][A-Z0-9]{2,9}` (VARCHAR(10), unique)
- Case-insensitive on input — the backend strips and uppercases before
  storing (this behavior predates the convention and is unchanged)

### Examples

| Code      | Department             |
| --------- | ---------------------- |
| `REC`     | Reception              |
| `TRIAGE`  | Triage & Vitals        |
| `CONSULT` | General Consultation   |
| `LAB`     | Laboratory             |
| `PHARM`   | Pharmacy               |

### Reserved codes (routing aliases)

The kiosk routing service resolves entry-type routing by department code.
These codes (or their accepted aliases) must exist for automatic routing to
work and **should not be reused for an unrelated department**:

| Routing behavior                        | Code(s) accepted            |
| --------------------------------------- | --------------------------- |
| Walk-in patients → reception            | `RECEPTION` or `REC`        |
| Emergency entry type → emergency dept   | `EMERGENCY`                 |
| Appointment entry type → triage         | `TRIAGE`                    |

A new deployment that renames these departments should keep the codes above
(the display name can differ; the code is what routing looks up).

### Choosing a new code

- Prefer a 3–5 letter mnemonic: `LAB`, `RAD`, `PHARM`, `OPD`
- Start with a letter; digits may appear after it (`XRAY2` is valid, `2XRAY` is not)
- No spaces, hyphens, or lowercase — the validator rejects them
- The code appears on public displays and admin tables; keep it readable

---

## 3. Where enforcement lives

| Rule                    | Location                                              |
| ----------------------- | ----------------------------------------------------- |
| Employee ID format      | `StaffBase.validate_employee_id` (`domain/schemas/schemas.py`) |
| Department code format  | `DepartmentBase.validate_department_code` + `DepartmentUpdate` validator (same file) |
| Uniqueness (both)       | DB unique constraints (`staff.employee_id`, `departments.department_code`) |
| Case normalization      | Schema validators (IDs/codes) + `departments_service` (code strip/upper) |

Both rules are enforced **only** through Pydantic schema validation, so no
alembic migration, no model change, and no service-layer changes were
required. Any future API client (admin dashboard, scripts, seeds)
gets the same validation for free.
