from uuid import uuid4
import pytest
import pytest_asyncio

from app.core.security import create_access_token, hash_password
from app.domain.models.models import Department, DeptType, Patient, Staff, StaffRole
from app.domain.services.patient_service import PatientService
from app.domain.services.queue_service import QueueService
from app.domain.services.routing_service import RoutingService
from app.domain.services.visit_service import VisitService
from app.domain.schemas.schemas import PatientCreate
from app.domain.models.models import EntryType, QueueEntry, QueueEntryStatus, QueuePriority
from app.domain.schemas.schemas import VisitCreate

# ---------------------------------------------------------------------------
# 1. Hospital Departments Suite (OPD, Triage, Emergency)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def routing_departments(db):
    """
    Creates standard hospital departments required by the routing workflow service.
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

# ---------------------------------------------------------------------------
# 2. Workflow Staff (Assigned to exact routing departments)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def receptionist(db, routing_departments):
    """
    Receptionist tied specifically to the Reception department created in routing_departments.
    """
    reception = routing_departments["reception"]

    staff = Staff(
        staff_id=uuid4(),
        employee_id="REC001",
        first_name="Alice",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        dept_id=reception.dept_id,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    # Attach generated JWT access token for integration tests
    staff.access_token = create_access_token({
        "sub": str(staff.staff_id),
        "employee_id": staff.employee_id,
        "role": staff.role.value if hasattr(staff.role, "value") else staff.role,
        "dept_id": str(staff.dept_id),
    })

    return staff


# ---------------------------------------------------------------------------
# 3. Service Bundle (Shared DB Transaction context across services)
# ---------------------------------------------------------------------------
@pytest.fixture
def services(db):
    """
    Instantiates domain services sharing the same test AsyncSession.
    """
    return {
        "patient": PatientService(db),
        "visit": VisitService(db),
        "routing": RoutingService(db),
        "queue": QueueService(db),
    }


# ---------------------------------------------------------------------------
# 4. Reception Workflow Context
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def reception_context(
    db,
    routing_departments,
    receptionist,
    services,
):
    return {
        "db": db,
        "services": services,
        "reception": routing_departments["reception"],
        "triage": routing_departments["triage"],
        "emergency": routing_departments["emergency"],
        "staff": receptionist,
    }

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



@pytest_asyncio.fixture
async def reception_queue_entry(db, reception_context, patient_factory):
    services = reception_context["services"]
    reception_dept = reception_context["reception"]

    patient = await patient_factory()

    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Reception Check-in",
        )
    )

    entry = QueueEntry(
        visit_id=visit.visit_id,
        department_id=reception_dept.dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )

    db.add(entry)
    await db.flush()  # <-- Changed from commit() to flush()
    return entry


# ---------------------------------------------------------------------------
# 6. Generic Queue Entry Factory Fixture (For dynamic contexts)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
def create_queue_entry(db):
    """
    Factory fixture allowing tests to manually generate queue entries 
    for any given department and visit context.
    """
    async def _create(visit_id, department_id, priority=QueuePriority.NORMAL):
        entry = QueueEntry(
            visit_id=visit_id,
            department_id=department_id,
            sequence_number=1,
            priority=priority,
            status=QueueEntryStatus.WAITING,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry

    return _create


@pytest_asyncio.fixture
async def triage_queue_entry(db, reception_context, patient_factory):
    """
    Creates an active Visit and a WAITING QueueEntry specifically
    assigned to the TRIAGE department.
    """
    services = reception_context["services"]
    triage_dept = reception_context["triage"]

    # 1. Create a patient
    patient = await patient_factory()

    # 2. Start a visit
    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Triage Check-in",
        )
    )

    # 3. Create Queue Entry in Triage Department
    entry = QueueEntry(
        visit_id=visit.visit_id,
        department_id=triage_dept.dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )

    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return entry