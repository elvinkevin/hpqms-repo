from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.security import create_access_token, hash_password
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
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
async def doctor_staff(db, department):
    staff = Staff(
        staff_id=uuid4(),
        employee_id="DOC001",
        dept_id=department.dept_id,
        first_name="Dr.",
        last_name="Smith",
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
    token = create_access_token({"sub": str(doctor_staff.staff_id)})
    return {"Authorization": f"Bearer {token}"}


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
async def active_visit(db, existing_patient):
    visit = Visit(
        patient_id=existing_patient.patient_id,
        token_number="W-101",
        entry_type=EntryType.WALK_IN,
        visit_reason="Routine Checkup",
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
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