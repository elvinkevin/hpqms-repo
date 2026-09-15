import os
from datetime import date
from uuid import uuid4


import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.security import create_access_token, hash_password
from app.core.config import settings
from app.db.session import Base, get_db
from app.domain.models.models import (
    Department,
    DeptType,
    EntryType,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    RegistrationStatus,
    Staff,
    StaffRole,
    Visit,
    VisitStage,
)
from app.domain.schemas.schemas import StaffCreate
from app.domain.services.staff_service import StaffService
from app.main import app

def make_headers(staff: Staff) -> dict:
    """Generate Authorization headers for a staff member."""
    token = create_access_token(
        {
            "sub": str(staff.staff_id),
            "employee_id": staff.employee_id,
            "role": staff.role.value if hasattr(staff.role, "value") else staff.role,
            "dept_id": str(staff.dept_id),
        }
    )
    return {"Authorization": f"Bearer {token}"}

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:viken@localhost/hospital_test",
)

# ============================================================================
# 1. DATABASE & ASYNC INFRASTRUCTURE
# ============================================================================


@pytest.fixture(scope="function")
def engine():
    return create_async_engine(
        DATABASE_URL,
        future=True,
        poolclass=NullPool,
    )


@pytest.fixture(scope="function", autouse=True)
async def create_database(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
def async_session_factory(engine):
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest.fixture(scope="function")
async def db(async_session_factory):
    async with async_session_factory() as session:
        yield session
        await session.rollback()


# ============================================================================
# 2. HTTP CLIENT & API FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    original_kiosk_key = settings.KIOSK_INTERNAL_API_KEY
    settings.KIOSK_INTERNAL_API_KEY = "test-kiosk-api-key"

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Kiosk-API-Key": settings.KIOSK_INTERNAL_API_KEY},
    ) as ac:
        yield ac
    settings.KIOSK_INTERNAL_API_KEY = original_kiosk_key
    app.dependency_overrides.clear()


# ============================================================================
# 3. CORE ENTITY FIXTURES
# ============================================================================


@pytest.fixture
async def patient(db):
    """Creates and persists a Patient record."""
    patient = Patient(
        first_name="Jane",
        last_name="Doe",
    )
    db.add(patient)
    await db.flush()
    await db.refresh(patient)
    return patient


@pytest.fixture
async def department(db):
    """Creates and persists an Outpatient Department record."""
    dept = Department(
        name="Outpatient",
        department_code="OPD",
        type=DeptType.OPD,
    )
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return dept


@pytest.fixture
async def secondary_department(db):
    """Creates and persists a Pharmacy Department record."""
    dept = Department(
        name="Pharmacy",
        department_code="PHARM",
        type=DeptType.OPD,
    )
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return dept


@pytest.fixture
async def active_visit(db, patient, department):
    """
    Creates and persists an active Visit record linked to a valid Patient,
    with a default WAITING QueueEntry already attached in `department`.

    Most routing/queue-transition tests operate on a visit that's already
    queued, so this fixture ships with an entry by default. Tests that need
    a bare Visit with no QueueEntry (e.g. queue_service creation tests that
    exercise `create_queue_entry` itself) override this fixture locally in
    their own test module — see test_queue_service.py.
    """
    visit = Visit(
        patient_id=patient.patient_id,
        token_number=f"W-{uuid4().int % 10**8:08d}",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.WALK_IN,
        visit_reason="General Consultation",
    )
    db.add(visit)
    await db.flush()

    entry = QueueEntry(
        visit_id=visit.visit_id,
        dept_id=department.dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add(entry)
    await db.flush()

    visit.current_queue_entry_id = entry.queue_entry_id
    await db.commit()
    await db.refresh(visit)
    return visit


@pytest.fixture
async def existing_patient(db):
    """Creates a fully registered patient with complete details."""
    patient = Patient(
        patient_id=uuid4(),
        first_name="Jane",
        last_name="Existing",
        national_id="99999999",
        phone="+254700000000",
        gender="FEMALE",
        date_of_birth=date(1995, 5, 15),
        registration_status=RegistrationStatus.COMPLETE,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


# ============================================================================
# 4. STAFF & AUTHENTICATION FIXTURES
# ============================================================================


@pytest.fixture
async def auth_staff(db, department):
    service = StaffService(db)
    staff = await service.create_staff(
        StaffCreate(
            employee_id="ADM001",
            first_name="System",
            last_name="Admin",
            role=StaffRole.ADMIN,
            dept_id=department.dept_id,
            password="Password123!",
        )
    )
    await db.commit()
    return staff


@pytest.fixture
async def auth_headers(client, auth_staff):
    response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": "ADM001",
            "password": "Password123!",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def staff_member(db, department):
    """
    Doctor/Staff fixture used in unit tests.
    Satisfies all schema contracts and is ready for state transitions.
    """
    staff = Staff(
        staff_id=uuid4(),
        employee_id=f"DOC-{str(uuid4())[:6]}",
        first_name="Test",
        last_name="Doctor",
        role=StaffRole.DOCTOR,
        dept_id=department.dept_id,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


@pytest_asyncio.fixture
async def receptionist_staff(db, department):
    """Creates a receptionist staff member."""
    staff = Staff(
        staff_id=uuid4(),
        employee_id="REC001",
        dept_id=department.dept_id,
        first_name="Alice",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


@pytest_asyncio.fixture
async def receptionist_token_headers(receptionist_staff):
    """Generates auth headers for receptionist."""
    return make_headers(receptionist_staff)


@pytest_asyncio.fixture
async def doctor_staff(db, department):
    """Creates a doctor staff member."""
    staff = Staff(
        staff_id=uuid4(),
        employee_id="DOC001",
        dept_id=department.dept_id,
        first_name="Dr",
        last_name="Doctor",
        role=StaffRole.DOCTOR,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


@pytest_asyncio.fixture
async def doctor_token_headers(doctor_staff):
    """Generates auth headers for doctor."""
    return make_headers(doctor_staff)


@pytest_asyncio.fixture
async def admin_staff(db, department):
    """Creates an admin staff member."""
    staff = Staff(
        staff_id=uuid4(),
        employee_id="ADM001",
        first_name="Admin",
        last_name="User",
        role=StaffRole.ADMIN,
        dept_id=department.dept_id,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


@pytest_asyncio.fixture
async def admin_headers(admin_staff):
    """Generates auth headers for admin."""
    return make_headers(admin_staff)


@pytest_asyncio.fixture
async def nurse_staff(db, department):
    """Creates a nurse staff member."""
    staff = Staff(
        staff_id=uuid4(),
        employee_id="NURSE002",
        dept_id=department.dept_id,
        first_name="Nurse",
        last_name="Jackie",
        role=StaffRole.NURSE,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


@pytest_asyncio.fixture
async def nurse_token_headers(nurse_staff):
    """Generates auth headers for nurse."""
    return make_headers(nurse_staff)


@pytest_asyncio.fixture
async def triage_nurse_staff(db, department):
    """Creates a triage nurse staff member."""
    staff = Staff(
        staff_id=uuid4(),
        employee_id="NURSE001",
        dept_id=department.dept_id,
        first_name="Nurse",
        last_name="Joy",
        role=StaffRole.TRIAGE_NURSE,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


@pytest_asyncio.fixture
async def triage_token_headers(triage_nurse_staff):
    """Generates auth headers for triage nurse."""
    return make_headers(triage_nurse_staff)


# ============================================================================
# 5. DEPARTMENT ROUTING FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def routing_departments(db):
    """
    Creates standard hospital departments required by routing workflows.
    Returns a dict with department keys for easy access.
    """
    departments = []

    configs = [
        ("Reception", "RECEPTION", DeptType.OPD),
        ("Triage", "TRIAGE", DeptType.OPD),
        ("Emergency", "EMERGENCY", DeptType.EMERGENCY),
    ]

    for name, code, dept_type in configs:
        department = Department(
            name=name,
            department_code=code,
            type=dept_type,
            is_active=True,
        )
        db.add(department)
        departments.append(department)

    await db.commit()

    for department in departments:
        await db.refresh(department)

    return {
        "reception": departments[0],
        "triage": departments[1],
        "emergency": departments[2],
    }


@pytest_asyncio.fixture
async def setup_departments(db):
    """
    Creates core hospital routing departments.
    Returns dict indexed by department code.
    """
    department_definitions = {
        "RECEPTION": {
            "name": "Reception",
            "type": DeptType.OPD,
        },
        "TRIAGE": {
            "name": "Triage",
            "type": DeptType.OPD,
        },
        "CONSULT": {
            "name": "Consultation",
            "type": DeptType.OPD,
        },
        "EMERGENCY": {
            "name": "Emergency",
            "type": DeptType.EMERGENCY,
        },
    }

    departments = {}

    for code, values in department_definitions.items():

        result = await db.execute(
            select(Department).where(
                Department.department_code == code
            )
        )

        dept = result.scalar_one_or_none()

        if dept is None:
            dept = Department(
                department_code=code,
                name=values["name"],
                type=values["type"],
                is_active=True,
            )

            db.add(dept)
            await db.flush()

        departments[code] = dept

    await db.commit()

    for dept in departments.values():
        await db.refresh(dept)

    return departments


# ============================================================================
# 6. QUEUE & VISIT FIXTURES FOR API TESTS
# ============================================================================


@pytest_asyncio.fixture
async def queue_entry(db, existing_patient, setup_departments):
    """
    Creates a complete visit with initial queue entry in WAITING status.
    Includes all relationships needed for API response serialization.
    """
    visit = Visit(
        patient_id=existing_patient.patient_id,
        token_number=f"W-{uuid4().int % 10**8:08d}",
        entry_type=EntryType.WALK_IN,
        visit_reason="Routine Checkup",
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
    await db.flush()

    # Automatically create initial queue entry in Reception
    entry = QueueEntry(
        visit_id=visit.visit_id,
        dept_id=setup_departments["RECEPTION"].dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add(entry)
    await db.flush()

    visit.current_queue_entry_id = entry.queue_entry_id
    await db.commit()
    await db.refresh(visit)
    await db.refresh(entry)
    return entry


@pytest_asyncio.fixture
async def reception_context(db, setup_departments):
    """
    Bundles everything a queue-workflow test needs:
    the reception department, a receptionist staff member, and
    ready-to-use visit/queue services sharing the test session.
    """
    from app.domain.services.visit_service import VisitService
    from app.domain.services.queue_service import QueueService

    reception = setup_departments["RECEPTION"]

    staff = Staff(
        staff_id=uuid4(),
        employee_id=f"REC-{uuid4().hex[:6]}",
        dept_id=reception.dept_id,
        first_name="Alice",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    return {
        "db": db,
        "reception": reception,
        "staff": staff,
        "services": {
            "visit": VisitService(db),
            "queue": QueueService(db),
        },
    }


@pytest_asyncio.fixture
async def patient_factory(db):
    """Factory creating distinct registered patients on demand."""
    from app.domain.models.models import RegistrationStatus
    from typing import Optional

    counter = {"n": 0}

    async def _create(
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ):
        counter["n"] += 1
        patient = Patient(
            patient_id=uuid4(),
            first_name=first_name or f"Walkin{counter['n']}",
            last_name=last_name or f"Patient{counter['n']}",
            national_id=f"NI-{uuid4().hex[:8]}",
            registration_status=RegistrationStatus.COMPLETE,
            is_active=True,
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)
        return patient

    return _create


@pytest_asyncio.fixture
async def reception_queue_entry(db, setup_departments, existing_patient):
    """Creates a WAITING queue entry in the RECEPTION department."""
    from app.domain.models.models import Visit as VisitModel

    reception = setup_departments["RECEPTION"]

    visit = VisitModel(
        patient_id=existing_patient.patient_id,
        token_number=f"W-{uuid4().int % 10**8:08d}",
        entry_type=EntryType.WALK_IN,
        visit_reason="Reception Check-in",
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
    await db.flush()

    entry = QueueEntry(
        visit_id=visit.visit_id,
        dept_id=reception.dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add(entry)
    visit.current_queue_entry_id = entry.queue_entry_id
    await db.commit()
    await db.refresh(entry)
    return entry


async def _create_receptionist_with_token(db, setup_departments, employee_id: str):
    """Creates a receptionist staff member plus an access token attribute."""
    reception = setup_departments["RECEPTION"]
    staff = Staff(
        staff_id=uuid4(),
        employee_id=employee_id,
        dept_id=reception.dept_id,
        first_name="Alice",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    staff.access_token = create_access_token(
        {
            "sub": str(staff.staff_id),
            "employee_id": staff.employee_id,
            "role": staff.role.value,
            "dept_id": str(staff.dept_id),
        }
    )
    return staff


@pytest_asyncio.fixture
async def receptionist(db, setup_departments):
    """Receptionist carrying an `access_token` attribute for header construction."""
    return await _create_receptionist_with_token(db, setup_departments, "REC-A1")


@pytest_asyncio.fixture
async def receptionist_two(db, setup_departments):
    """Second receptionist in the same department, with an access token."""
    return await _create_receptionist_with_token(db, setup_departments, "REC-B2")


@pytest_asyncio.fixture
async def create_no_show_entry(db, setup_departments, existing_patient):
    """Factory creating a no-show queue entry assigned to a staff member."""
    from app.domain.models.models import Visit as VisitModel

    reception = setup_departments["RECEPTION"]
    visit_counter = {"n": 0}

    async def _create(assigned_staff_id):
        visit_counter["n"] += 1
        visit = VisitModel(
            patient_id=existing_patient.patient_id,
            token_number=f"W-{uuid4().int % 10**8:08d}",
            entry_type=EntryType.WALK_IN,
            visit_reason="No-show Test",
            stage=VisitStage.ACTIVE,
        )
        db.add(visit)
        await db.flush()

        entry = QueueEntry(
            visit_id=visit.visit_id,
            dept_id=reception.dept_id,
            sequence_number=visit_counter["n"],
            priority=QueuePriority.NORMAL,
            status=QueueEntryStatus.NO_SHOW,
            assigned_staff_id=assigned_staff_id,
        )
        db.add(entry)
        visit.current_queue_entry_id = entry.queue_entry_id
        await db.commit()
        await db.refresh(entry)
        return entry

    return _create


# ============================================================================
# 7. HELPER UTILITIES
# ============================================================================


@pytest_asyncio.fixture
async def create_helper_visit(db, patient):
    """
    Factory fixture to create additional distinct visits for the same patient.
    Useful for testing queue ordering with multiple entries.
    """
    async def _create_visit(token_number: str):
        visit = Visit(
            patient_id=patient.patient_id,
            token_number=token_number,
            stage=VisitStage.ACTIVE,
            entry_type=EntryType.WALK_IN,
        )
        db.add(visit)
        await db.flush()
        await db.refresh(visit)
        return visit

    return _create_visit