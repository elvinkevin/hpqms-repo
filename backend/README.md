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



async def register_standard_patient(self, data: PatientCreate) -> Patient:
        """
        Standard demographic registration for planned or non-emergency visits.
        """
        # Centralized Identity Check
        await self._validate_unique_identity(
            national_id=data.national_id,
            phone=data.phone,
        )

        patient = Patient(
            **data.model_dump(),
            registration_status=RegistrationStatus.COMPLETE,
        )

        try:
            self.db.add(patient)
            await self.db.flush()
            await self.db.refresh(patient)
            return patient
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not register patient due to a database integrity constraint.",
            )

class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (Index("idx_patient_name", "first_name", "last_name"),)

    patient_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Workflow & Identity Management
    registration_status = Column(
        Enum(RegistrationStatus),
        nullable=False,
        server_default=RegistrationStatus.INCOMPLETE.value,
    )
    temporary_identifier = Column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        comment="System-generated ID for John Doe / Emergency intake (e.g., TEMP-20260728-992)",
    )
    national_id = Column(String(20), unique=True, nullable=True, index=True)

    # Demographics
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    date_of_birth = Column(Date, nullable=True)
    estimated_age = Column(
        Integer,
        nullable=True,
        comment="Used during emergency intake when exact DOB is unknown",
    )
    gender = Column(String(20))
    email = Column(String(255))

    # Medical Info
    blood_type = Column(String(10))
    allergies = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default="true")

    # Audit & Identity Reconciliation Tracking
    reconciled_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when temporary identity was reconciled to official details",
    )
    reconciled_by = Column(
        UUID(as_uuid=True),
        ForeignKey("staff.staff_id"),
        nullable=True,
        comment="User ID of staff member who performed identity reconciliation",
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Domain Helper Properties
    @property
    def is_temporary(self) -> bool:
        """Convenience check for unreconciled/emergency records."""
        return self.registration_status == RegistrationStatus.INCOMPLETE

    # Relationships
    visits = relationship("Visit", back_populates="patient")
    appointments = relationship("Appointment", back_populates="patient")
    
    # FIXED: Use the Python Class Name "Staff" (or explicit Patient.reconciled_by)
    reconciler = relationship(
        "Staff", foreign_keys="[Patient.reconciled_by]", backref="reconciled_patients"
    )

ChatGPT said:
Perfect. This confirms the intended design: an unknown kiosk identifier can create an INCOMPLETE patient, which then naturally routes to Reception.

There is one important correction to the earlier implementation: we should not create a patient with national_id=identifier blindly, because the identifier may actually be a phone number.

1. Add a kiosk-specific patient registration method
In PatientService:

async def register_kiosk_patient(
    self,
    identifier: str,
) -> Patient:
    """
    Creates the minimal patient record required for kiosk check-in.

    The identifier may be a national ID or phone number.
    The patient remains INCOMPLETE and is completed later by Reception.
    """

    identifier = identifier.strip()

    # Don't allow the kiosk to create a duplicate identity.
    existing = await self.find_patient_optional(identifier)

    if existing:
        return existing

    # Determine what kind of identifier was supplied.
    #
    # This intentionally stays simple: if it matches an existing
    # national ID format we store it as national_id; otherwise we
    # treat it as a phone number.
    #
    # We can tighten this validation later based on your country's
    # actual identifier/phone rules.

    patient_kwargs = {
        "registration_status": RegistrationStatus.INCOMPLETE,
    }

    if identifier.isdigit() and len(identifier) >= 9:
        patient_kwargs["phone"] = identifier
    else:
        patient_kwargs["national_id"] = identifier

    patient = Patient(**patient_kwargs)

    try:
        self.db.add(patient)
        await self.db.flush()
        await self.db.refresh(patient)
        return patient

    except IntegrityError:
        await self.db.rollback()

        # Another request may have created the same identity
        # concurrently.
        existing = await self.find_patient_optional(identifier)

        if existing:
            return existing

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create kiosk patient.",
        )

However, I want to make one improvement before we commit to the isdigit() rule: phone numbers and national IDs are domain-specific, so eventually I'd rather have explicit validation/normalization instead of guessing based on length.

For now, this gets the architecture moving.

2. Add the optional lookup
You currently have:

async def find_patient(self, query: str) -> Patient:

Keep that method exactly as it is because your existing:

GET /api/patients/find/{identifier}

needs its 404.

Add:

async def find_patient_optional(
    self,
    query: str,
) -> Patient | None:
    result = await self.db.execute(
        select(Patient).where(
            or_(
                Patient.national_id == query,
                Patient.phone == query,
                Patient.temporary_identifier == query,
            )
        )
    )

    return result.scalar_one_or_none()

3. Build KioskService
Now we can make the orchestration service properly.

app/domain/services/kiosk_service.py:

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.schemas import (
    KioskCheckInRequest,
    VisitCreate,
)
from app.domain.services.patient_service import PatientService
from app.domain.services.visit_service import VisitService
from app.domain.services.routing_service import RoutingService


class KioskService:

    def __init__(self, db: AsyncSession):
        self.db = db

        self.patient_service = PatientService(db)
        self.visit_service = VisitService(db)
        self.routing_service = RoutingService(db)

    async def check_in(
        self,
        data: KioskCheckInRequest,
    ):
        identifier = data.identifier.strip()

        if not identifier:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Patient identifier cannot be empty.",
            )

        # ----------------------------------------------------------
        # 1. Find existing patient
        # ----------------------------------------------------------

        patient = await self.patient_service.find_patient_optional(
            identifier
        )

        # ----------------------------------------------------------
        # 2. Create incomplete patient if necessary
        # ----------------------------------------------------------

        if patient is None:
            patient = await self.patient_service.register_kiosk_patient(
                identifier
            )

        # ----------------------------------------------------------
        # 3. Start visit
        # ----------------------------------------------------------

        visit = await self.visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=data.visit_type,
                visit_reason="Kiosk check-in",
            )
        )

        # ----------------------------------------------------------
        # 4. Apply routing rules
        # ----------------------------------------------------------

        queue_entry = (
            await self.routing_service.dispatch_initial_kiosk_route(
                visit_id=visit.visit_id
            )
        )

        # ----------------------------------------------------------
        # 5. Return complete kiosk result
        # ----------------------------------------------------------

        return patient, visit, queue_entry

This is the important architecture:

KioskService
    │
    ├── PatientService
    │      └── find/create patient
    │
    ├── VisitService
    │      └── generate token + create visit
    │
    └── RoutingService
           └── determine department

The kiosk itself doesn't need to know any of those rules.

4. Add the endpoint
Create something like:

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.schemas.schemas import (
    KioskCheckInRequest,
    KioskCheckInResponse,
)
from app.domain.services.kiosk_service import KioskService


router = APIRouter(
    prefix="/kiosk",
    tags=["Kiosk"],
)


@router.post(
    "/check-in",
    response_model=KioskCheckInResponse,
    status_code=status.HTTP_201_CREATED,
)
async def kiosk_check_in(
    data: KioskCheckInRequest,
    db: AsyncSession = Depends(get_db),
):
    service = KioskService(db)

    patient, visit, queue_entry = await service.check_in(data)

    await db.commit()

    return KioskCheckInResponse(
        patient=patient,
        visit=visit,
        queue=queue_entry,
    )

Then register this router wherever you register the other API routers.

5. One important issue: QueueEntryRead
Your dispatch_initial_kiosk_route() eventually calls transfer_patient().

That means the returned queue entry needs to be sufficiently loaded for:

QueueEntryRead

and particularly:

visit: Optional[VisitRead]

If transfer_patient() returns an object with unloaded relationships, we could hit the same MissingGreenlet problem you just fixed in the requeue test.

So before testing the endpoint, inspect the final transfer_patient() implementation.

We want it to return a queue entry whose required relationships are eagerly loaded, something along the lines of:

selectinload(QueueEntry.visit)

and, if VisitRead contains patient:

selectinload(QueueEntry.visit).selectinload(Visit.patient)

This is especially important because the kiosk response will be serialized after the service returns.

6. The resulting frontend contract
Once this is in place, your frontend becomes extremely simple.

Request
POST /api/kiosk/check-in
Content-Type: application/json

{
  "identifier": "0712345678",
  "visit_type": "WALK_IN"
}

Response
Conceptually:

{
  "patient": {
    "patient_id": "...",
    "first_name": null,
    "last_name": null,
    "phone": "0712345678",
    "registration_status": "INCOMPLETE"
  },
  "visit": {
    "visit_id": "...",
    "token_number": "W-101",
    "entry_type": "WALK_IN",
    "stage": "ACTIVE"
  },
  "queue": {
    "queue_entry_id": "...",
    "department_id": "...",
    "status": "WAITING",
    "priority": "NORMAL"
  }
}

The frontend then displays:

CHECK-IN SUCCESSFUL

Token: W-101

Please proceed to:
RECEPTION

Your registration will be
completed at the desk.

For an existing complete patient:

identifier
    ↓
existing patient
    ↓
start visit
    ↓
W-102
    ↓
RECEPTION

For an appointment:

identifier
    ↓
existing patient
    ↓
APPOINTMENT
    ↓
A-203
    ↓
TRIAGE

And emergency:

identifier
    ↓
EMERGENCY
    ↓
CRITICAL
    ↓
EMERGENCY department

One thing I would change before writing tests
Your current kiosk requirements say the kiosk collects identifier + visit type, but EMERGENCY is potentially different operationally because your existing emergency workflow supports John Doe / temporary patients.

So for the first implementation, I'd make the contract explicit:

class KioskCheckInRequest(BaseModel):
    identifier: str
    visit_type: EntryType

and support:

WALK_IN → yes
APPOINTMENT → yes
REFERRAL → yes
EMERGENCY → only if an identifiable patient exists
Then keep your existing /patients/emergency endpoint for the clinical John Doe emergency intake flow. That avoids accidentally creating an incomplete normal patient when an emergency patient should receive a temporary identifier.

Next, we should inspect transfer_patient() and VisitRead before running the kiosk tests. Those are the two places most likely to expose relationship-loading/serialization issues given the MissingGreenlet problems you've just encountered.



ChatGPT is AI and can make mistakes.

