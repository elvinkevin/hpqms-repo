# HPQMS Backend — Phase 1

## Prerequisites
- Python 3.11+
- PostgreSQL 15+ running locally
- `pip` (or `pip3`)

---

## Setup in 5 commands

```bash
# 1. Clone the repo and enter backend
cd hpqms/backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file
cp .env.example .env
# Edit .env: set DATABASE_URL, SECRET_KEY

# 5. Create the database
psql -U postgres -c "CREATE DATABASE hpqms;"
```

## Run migrations and seed

```bash
# Generate first migration (auto-detects all models)
alembic revision --autogenerate -m "initial schema"

# Apply migrations
alembic upgrade head

# Seed departments, staff, and test patient
python scripts/seed.py
```

## Start the server

```bash
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

---

## Test accounts (after seed)

| Employee ID | Password       | Role         | Department  |
|-------------|----------------|--------------|-------------|
| REC-001     | reception123   | RECEPTIONIST | General OPD |
| NRS-001     | nurse123       | TRIAGE_NURSE | General OPD |
| NRS-002     | nurse123       | CHARGE_NURSE | Emergency   |
| DOC-001     | doctor123      | DOCTOR       | General OPD |
| DOC-002     | doctor123      | DOCTOR       | Cardiology  |

Test patient national ID: `12345678`

---

## Run tests

```bash
# Unit tests (no DB required)
pytest tests/unit/ -v

# All tests (requires running DB)
pytest -v
```

---

## Key endpoints

| Method | Path                          | Role needed        | What it does                    |
|--------|-------------------------------|--------------------|---------------------------------|
| POST   | /api/v1/auth/login            | —                  | Login, returns JWT              |
| POST   | /api/v1/patients              | RECEPTIONIST       | Register new patient            |
| GET    | /api/v1/patients/{nat_id}     | Any staff          | Lookup patient by national ID   |
| POST   | /api/v1/tokens                | RECEPTIONIST       | Issue a walk-in token           |
| PATCH  | /api/v1/tokens/{id}/status    | Any staff          | Update token status             |
| GET    | /api/v1/tokens/{id}/wait      | Any staff          | Get estimated wait in minutes   |
| GET    | /api/v1/queues/{dept_id}/tokens | Any staff        | Ordered active queue for dept   |

---

## Project structure

```
backend/
├── app/
│   ├── main.py                     ← FastAPI app, CORS, router mount
│   ├── api/v1/
│   │   ├── router.py               ← Registers all endpoint routers
│   │   └── endpoints/
│   │       ├── auth.py             ← POST /auth/login
│   │       ├── patients.py         ← Patient registration and lookup
│   │       ├── tokens.py           ← Token issuance and status updates
│   │       └── queues.py           ← Ordered queue list per department
│   ├── core/
│   │   ├── config.py               ← Settings from .env
│   │   └── security.py             ← JWT encode/decode, password hashing
│   ├── db/
│   │   └── session.py              ← Async engine, Base, get_db()
│   └── domain/
│       ├── models/models.py        ← All SQLAlchemy ORM models + enums
│       ├── schemas/schemas.py      ← All Pydantic request/response shapes
│       └── services/
│           ├── queue_service.py    ← Core queue logic (reorder, issue, transition)
│           ├── patient_service.py  ← Registration + lookup
│           ├── auth_service.py     ← Login, JWT, role guards
│           └── audit_service.py    ← Append-only audit log writer
├── alembic/                        ← Database migrations
├── scripts/seed.py                 ← Initial data seeder
├── tests/
│   └── unit/test_queue_logic.py   ← 20 unit tests, no DB required
├── requirements.txt
└── .env.example
```

Client
   │
   ▼
POST /patients
   │
   ▼
FastAPI
   │
   ├── Validate request body (PatientCreate)
   ├── Open database session (get_db)
   ├── Authenticate user (get_current_user)
   └── Check role (require_role)
   │
   ▼
register_patient()
   │
   ▼
PatientService.register()
   │
   ▼
Database
   │
   ▼
Patient created
   │
   ▼
Log audit action
   │
   ▼
Convert to PatientRead
   │
   ▼
Return HTTP 201 response


patients registry process
1. User sends patient details.
authorization and verification phase
From auth_service.py:
2. Backend checks that the user is logged in.
3. Backend checks that the user is RECEPTIONIST or ADMIN.
service/business layer
From patient_service.py:
4. Backend checks whether national_id already exists.
5. If duplicate, request fails.
6. If not duplicate, backend creates patient.
audit layer
From audit_service.py:
7. Backend records audit log.
8. Backend returns created patient.
