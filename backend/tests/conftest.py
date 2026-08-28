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
from tests.api.test_routing_api import make_headers

DATABASE_URL = "postgresql+asyncpg://postgres:viken@localhost/hospital_test"

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
# 3. BASE DEPARTMENT & STAFF FIXTURES
# ============================================================================


@pytest.fixture
async def department(db):
    department = Department(
        name="Reception",
        department_code="REC",
        type=DeptType.OPD,
    )
    db.add(department)
    await db.commit()
    await db.refresh(department)
    return department


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
async def receptionist_staff(db, department):
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
    token = create_access_token({"sub": str(receptionist_staff.staff_id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def doctor_staff(doctor):
    return doctor


@pytest_asyncio.fixture
async def doctor_token_headers(doctor_staff):
    return make_headers(doctor_staff)


@pytest_asyncio.fixture
async def admin_staff(db, department):
    staff = Staff(
        employee_id="ADM001",
        first_name="Admin",
        last_name="User",
        role=StaffRole.ADMIN,
        dept_id=department.dept_id,
        hashed_password="ignored",
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


@pytest_asyncio.fixture
async def admin_headers(admin_staff):
    return make_headers(admin_staff)


# ============================================================================
# 4. LEGACY ENTITY FIXTURES (Unit/API testing only)
# ============================================================================


@pytest_asyncio.fixture
async def existing_patient(db):
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


@pytest_asyncio.fixture
async def active_visit(db, existing_patient, setup_departments):
    visit = Visit(
        patient_id=existing_patient.patient_id,
        token_number="W-101",
        entry_type=EntryType.WALK_IN,
        visit_reason="Routine Checkup",
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
    await db.flush()

    # Automatically create initial queue entry in Reception
    entry = QueueEntry(
        visit_id=visit.visit_id,
        department_id=setup_departments["RECEPTION"].dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add(entry)

    await db.commit()
    await db.refresh(visit)
    return visit


@pytest_asyncio.fixture
async def queue_entry(db, active_visit, department):
    entry = QueueEntry(
        visit_id=active_visit.visit_id,
        department_id=department.dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry



import pytest_asyncio

@pytest_asyncio.fixture
async def patient_factory(db, faker):
    async def _create_patient(**kwargs):
        defaults = {
            "first_name": faker.first_name(),
            "last_name": faker.last_name(),
            "gender": "MALE",
            "date_of_birth": faker.date_of_birth(),
            "phone": faker.phone_number(),
        }
        defaults.update(kwargs)
        patient = Patient(**defaults)
        db.add(patient)
        await db.flush()
        return patient

    return _create_patient


@pytest.fixture
async def patient(db):
    """Creates and persists a Patient parent record."""
    patient = Patient(
        first_name="Jane",
        last_name="Doe",
    )
    db.add(patient)
    await db.flush()
    await db.refresh(patient)
    return patient


@pytest_asyncio.fixture
async def setup_departments(db):
    """
    Creates (or reuses) the core hospital routing departments.
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


@pytest_asyncio.fixture
async def triage_nurse_staff(db, setup_departments):
    """
    Creates or reuses a triage nurse staff member.
    """
    from sqlalchemy import select

    result = await db.execute(
        select(Staff).where(Staff.employee_id == "NURSE001")
    )
    staff = result.scalar_one_or_none()

    if staff is None:
        triage_dept = setup_departments.get("TRIAGE") or setup_departments.get("RECEPTION")
        staff = Staff(
            staff_id=uuid4(),
            employee_id="NURSE001",
            dept_id=triage_dept.dept_id,
            first_name="Nurse",
            last_name="Joy",
            role=StaffRole.TRIAGE_NURSE,  # Adjust to StaffRole.NURSE if your Enum uses that
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(staff)
        await db.commit()
        await db.refresh(staff)

    return staff


@pytest_asyncio.fixture
async def triage_token_headers(triage_nurse_staff):
    """
    Generates auth headers for the triage nurse.
    """
    token = create_access_token({"sub": str(triage_nurse_staff.staff_id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def nurse_staff(db, setup_departments):
    """
    Creates or reuses a standard nurse staff member.
    """
    from sqlalchemy import select

    result = await db.execute(
        select(Staff).where(Staff.employee_id == "NURSE002")
    )
    staff = result.scalar_one_or_none()

    if staff is None:
        dept = setup_departments.get("CONSULT") or setup_departments.get("RECEPTION")
        staff = Staff(
            staff_id=uuid4(),
            employee_id="NURSE002",
            dept_id=dept.dept_id,
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
    """
    Generates auth headers for the nurse.
    """
    token = create_access_token({"sub": str(nurse_staff.staff_id)})
    return {"Authorization": f"Bearer {token}"}