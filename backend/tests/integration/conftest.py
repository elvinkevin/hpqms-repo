from uuid import uuid4
import pytest
import pytest_asyncio

from app.core.security import hash_password
from app.domain.models.models import Department, DeptType, Staff, StaffRole
from app.domain.services.patient_service import PatientService
from app.domain.services.queue_service import QueueService
from app.domain.services.routing_service import RoutingService
from app.domain.services.visit_service import VisitService


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
@pytest.fixture
async def reception_context(
    db,
    routing_departments,
    receptionist,
    services,
):
    """
    Bundles together all infrastructure and actors required to execute 
    and assert full reception/check-in integration tests.
    """
    return {
        "db": db,
        "services": services,
        "reception": routing_departments["reception"],
        "triage": routing_departments["triage"],
        "emergency": routing_departments["emergency"],
        "staff": receptionist,
    }