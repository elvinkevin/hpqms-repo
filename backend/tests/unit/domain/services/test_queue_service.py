import uuid
import pytest
from datetime import datetime
from fastapi import HTTPException, status
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from uuid import uuid4
from app.domain.models.models import (
    Department,
    DeptType,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    EntryType,
    StaffRole,
    Visit,
    VisitStage,
    Staff,
)
from app.domain.services.queue_service import QueueService


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
async def queue_service(db):
    """Provides a fresh QueueService instance bound to the active async database session."""
    return QueueService(db)


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


@pytest.fixture
async def department(db):
    """Creates and persists an Outpatient Department record."""
    dept = Department(
        name="Outpatient",
        department_code="OPD",
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
    )
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return dept


@pytest.fixture
async def active_visit(db, patient):
    """Creates and persists an active Visit record linked to a valid Patient."""
    visit = Visit(
        patient_id=patient.patient_id,
        token_number="W-101",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.WALK_IN,
        visit_reason="General Consultation",
    )
    db.add(visit)
    await db.flush()
    await db.refresh(visit)
    return visit


async def create_helper_visit(db, patient, token_number):
    """Helper utility to generate additional distinct visits."""
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


@pytest_asyncio.fixture
async def staff_member(db, routing_departments):
    """
    Doctor/Staff fixture used in the unit tests that satisfies all schema contracts.
    """
    # Fix: Use an existing key from your routing_departments fixture
    triage_dept = routing_departments["triage"] 

    staff = Staff(
        staff_id=uuid4(),
        employee_id=f"DOC-{str(uuid4())[:6]}",
        first_name="Test",
        last_name="Doctor",
        role=StaffRole.DOCTOR,
        dept_id=triage_dept.dept_id,             # Uses the valid department ID
        hashed_password="mock_hashed_password",   # Satisfies the NOT NULL constraint
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff




# ==============================================================================
# 1. CREATE CATEGORY
# ==============================================================================

@pytest.mark.asyncio
async def test_create_queue_entry(queue_service, active_visit, department):
    """Verifies successful creation of a new queue entry in WAITING status."""
    entry = await queue_service.create_queue_entry(
        visit_id=active_visit.visit_id,
        department_id=department.dept_id,
        priority=QueuePriority.NORMAL,
        notes="Standard triage check",
    )

    assert entry.visit_id == active_visit.visit_id
    assert entry.department_id == department.dept_id
    assert entry.status == QueueEntryStatus.WAITING
    assert entry.sequence_number == 1
    assert entry.notes == "Standard triage check"


@pytest.mark.asyncio
async def test_duplicate_active_queue(queue_service, active_visit, department):
    """Ensures duplicate active queue entries on the same visit trigger a unique constraint error."""
    await queue_service.create_queue_entry(
        visit_id=active_visit.visit_id,
        department_id=department.dept_id,
    )

    with pytest.raises((HTTPException, IntegrityError)):
        await queue_service.create_queue_entry(
            visit_id=active_visit.visit_id,
            department_id=department.dept_id,
        )


@pytest.mark.asyncio
async def test_unknown_visit(queue_service, department):
    """Verifies creating a queue entry with an invalid visit ID fails FK constraints/validations."""
    with pytest.raises((HTTPException, IntegrityError)):
        await queue_service.create_queue_entry(
            visit_id=uuid.uuid4(),
            department_id=department.dept_id,
        )


@pytest.mark.asyncio
async def test_unknown_department(queue_service, active_visit):
    """Verifies routing a visit to an invalid department ID fails FK constraints/validations."""
    with pytest.raises((HTTPException, IntegrityError)):
        await queue_service.create_queue_entry(
            visit_id=active_visit.visit_id,
            department_id=uuid.uuid4(),
        )


# ==============================================================================
# 2. READ CATEGORY
# ==============================================================================

@pytest.mark.asyncio
async def test_get_queue_entry(queue_service, active_visit, department):
    """Validates fetching a single queue entry by primary key with joined models loaded."""
    created = await queue_service.create_queue_entry(
        visit_id=active_visit.visit_id,
        department_id=department.dept_id,
    )

    retrieved = await queue_service.get_queue_entry(created.queue_entry_id)

    assert retrieved.queue_entry_id == created.queue_entry_id
    assert retrieved.department.department_code == "OPD"
    assert retrieved.visit.patient is not None


@pytest.mark.asyncio
async def test_unknown_queue_entry(queue_service):
    """Ensures requesting a non-existent queue entry UUID raises HTTP 404."""
    with pytest.raises(HTTPException) as exc:
        await queue_service.get_queue_entry(uuid.uuid4())

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_department_queue(queue_service, db, patient, active_visit, department):
    """Verifies that retrieving a department queue returns active entries ordered correctly."""
    v1 = active_visit
    v2 = await create_helper_visit(db, patient, "W-102")

    e1 = await queue_service.create_queue_entry(visit_id=v1.visit_id, department_id=department.dept_id)
    e2 = await queue_service.create_queue_entry(visit_id=v2.visit_id, department_id=department.dept_id)

    queue = await queue_service.get_department_queue(department.dept_id)

    assert len(queue) == 2
    assert queue[0].queue_entry_id == e1.queue_entry_id
    assert queue[1].queue_entry_id == e2.queue_entry_id


@pytest.mark.asyncio
async def test_get_next_patient(queue_service, db, patient, active_visit, department):
    """Validates fetching the next waiting patient in line based on priority and sequence."""
    e1 = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)

    next_up = await queue_service.get_next_patient(department.dept_id)

    assert next_up is not None
    assert next_up.queue_entry_id == e1.queue_entry_id


# ==============================================================================
# 3. STATUS TRANSITIONS CATEGORY
# ==============================================================================



@pytest.mark.asyncio
async def test_cancel_queue_entry(queue_service, active_visit, department):
    """Verifies cancelling an active entry at any valid stage."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)

    cancelled = await queue_service.cancel_queue_entry(entry.queue_entry_id, notes="Patient requested cancellation")

    assert cancelled.status == QueueEntryStatus.CANCELLED
    assert cancelled.completed_at is not None



# ==============================================================================
# 4. ORDERING & PRIORITY CATEGORY
# ==============================================================================

@pytest.mark.asyncio
async def test_fifo_order(queue_service, db, patient, active_visit, department):
    """Validates First-In, First-Out queue ordering for same priority tickets."""
    v1 = active_visit
    v2 = await create_helper_visit(db, patient, "W-102")

    e1 = await queue_service.create_queue_entry(visit_id=v1.visit_id, department_id=department.dept_id, priority=QueuePriority.NORMAL)
    e2 = await queue_service.create_queue_entry(visit_id=v2.visit_id, department_id=department.dept_id, priority=QueuePriority.NORMAL)

    first = await queue_service.get_next_patient(department.dept_id)
    assert first.queue_entry_id == e1.queue_entry_id


@pytest.mark.asyncio
async def test_priority_order(queue_service, db, patient, active_visit, department):
    """Validates that a higher priority ticket jumps ahead of earlier normal priority tickets."""
    v1 = active_visit
    v2 = await create_helper_visit(db, patient, "E-101")

    # Lower priority first
    await queue_service.create_queue_entry(visit_id=v1.visit_id, department_id=department.dept_id, priority=QueuePriority.NORMAL)
    # Critical priority second
    e2 = await queue_service.create_queue_entry(visit_id=v2.visit_id, department_id=department.dept_id, priority=QueuePriority.CRITICAL)

    next_up = await queue_service.get_next_patient(department.dept_id)
    assert next_up.queue_entry_id == e2.queue_entry_id





@pytest.mark.asyncio
async def test_empty_queue(queue_service, department):
    """Validates get_next_patient returns None when queue has no waiting entries."""
    next_up = await queue_service.get_next_patient(department.dept_id)
    assert next_up is None


# ==============================================================================
# 5. SEQUENCE MANAGEMENT CATEGORY
# ==============================================================================

@pytest.mark.asyncio
async def test_first_sequence(queue_service, active_visit, department):
    """Verifies the first ticket of the day in a department gets sequence number 1."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    assert entry.sequence_number == 1


@pytest.mark.asyncio
async def test_increment_sequence(queue_service, db, patient, active_visit, department):
    """Verifies subsequent entries in a department auto-increment monotonically."""
    v1 = active_visit
    v2 = await create_helper_visit(db, patient, "W-102")

    e1 = await queue_service.create_queue_entry(visit_id=v1.visit_id, department_id=department.dept_id)
    e2 = await queue_service.create_queue_entry(visit_id=v2.visit_id, department_id=department.dept_id)

    assert e1.sequence_number == 1
    assert e2.sequence_number == 2


@pytest.mark.asyncio
async def test_independent_departments(queue_service, db, patient, active_visit, department, secondary_department):
    """Verifies sequence numbers increment independently per department."""
    v1 = active_visit
    v2 = await create_helper_visit(db, patient, "W-102")

    e1 = await queue_service.create_queue_entry(visit_id=v1.visit_id, department_id=department.dept_id)
    e2 = await queue_service.create_queue_entry(visit_id=v2.visit_id, department_id=secondary_department.dept_id)

    assert e1.sequence_number == 1
    assert e2.sequence_number == 1


# ==============================================================================
# 6. VISIT ENCOUNTER HELPERS
# ==============================================================================

@pytest.mark.asyncio
async def test_visit_updated(queue_service, active_visit, department):
    """Verifies active entry resolution correctly maps to the corresponding visit entity."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)

    active_entry = await queue_service.get_active_queue_entry(active_visit.visit_id)
    assert active_entry is not None
    assert active_entry.queue_entry_id == entry.queue_entry_id


@pytest.mark.asyncio
async def test_visit_cleared(queue_service, active_visit, department):
    """Ensures completing or cancelling a ticket clears active visit status lookup."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    await queue_service.cancel_queue_entry(entry.queue_entry_id)

    active_entry = await queue_service.get_active_queue_entry(active_visit.visit_id)
    assert active_entry is None


# ==============================================================================
# 7. EDGE CASES & STATE VALIDATION
# ==============================================================================

@pytest.mark.asyncio
async def test_invalid_transition(queue_service, active_visit, department):
    """Ensures illegal state moves (e.g. WAITING directly to IN_PROGRESS) raise 422 HTTP exception."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)

    with pytest.raises(HTTPException) as exc:
        await queue_service.transition_entry_status(entry.queue_entry_id, QueueEntryStatus.IN_PROGRESS)

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_duplicate_queue(queue_service, active_visit, department):
    """Re-verifies active duplicate entry guardrails on the same visit encounter."""
    await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)

    with pytest.raises((HTTPException, IntegrityError)):
        await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)


@pytest.mark.asyncio
async def test_cancelled_entry(queue_service, active_visit, department):
    """Confirms cancelled terminal state prevents any further state transitions."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    await queue_service.cancel_queue_entry(entry.queue_entry_id)

    with pytest.raises(HTTPException) as exc:
        await queue_service.transition_entry_status(entry.queue_entry_id, QueueEntryStatus.WAITING)

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_call_patient(queue_service, active_visit, department, staff_member):
    """Verifies transitioning status from WAITING -> CALLED and setting timestamp."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)

    called = await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.CALLED,
        staff_id=staff_member.staff_id,
    )

    assert called.status == QueueEntryStatus.CALLED
    assert isinstance(called.called_at, datetime)


@pytest.mark.asyncio
async def test_start_consultation(queue_service, active_visit, department, staff_member):
    """Verifies transitioning status from CALLED -> IN_PROGRESS and setting started_at timestamp."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.CALLED,
        staff_id=staff_member.staff_id,
    )

    started = await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=staff_member.staff_id,
    )

    assert started.status == QueueEntryStatus.IN_PROGRESS
    assert isinstance(started.started_at, datetime)


@pytest.mark.asyncio
async def test_complete_queue_entry(queue_service, active_visit, department, staff_member):
    """Verifies transitioning status from IN_PROGRESS -> COMPLETED."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.CALLED,
        staff_id=staff_member.staff_id,
    )
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=staff_member.staff_id,
    )

    completed = await queue_service.complete_queue_entry(
        queue_entry_id=entry.queue_entry_id,
        staff_id=staff_member.staff_id,
        notes="Finished exam",
    )

    assert completed.status == QueueEntryStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.notes == "Finished exam"


@pytest.mark.asyncio
async def test_mark_no_show(queue_service, active_visit, department, staff_member):
    """Verifies transitioning CALLED -> NO_SHOW."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.CALLED,
        staff_id=staff_member.staff_id,
    )

    no_show = await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.NO_SHOW,
        staff_id=staff_member.staff_id,
    )

    assert no_show.status == QueueEntryStatus.NO_SHOW
    assert no_show.no_show_at is not None
    assert no_show.completed_at is None


@pytest.mark.asyncio
async def test_completed_not_returned(queue_service, active_visit, department, staff_member):
    """Ensures completed tickets are excluded from active department queue calls."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.CALLED,
        staff_id=staff_member.staff_id,
    )
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=staff_member.staff_id,
    )
    await queue_service.complete_queue_entry(
        queue_entry_id=entry.queue_entry_id,
        staff_id=staff_member.staff_id,
    )

    queue = await queue_service.get_department_queue(department.dept_id)
    assert len(queue) == 0


@pytest.mark.asyncio
async def test_completed_entry(queue_service, active_visit, department, staff_member):
    """Confirms completed terminal state prevents any further state transitions."""
    entry = await queue_service.create_queue_entry(visit_id=active_visit.visit_id, department_id=department.dept_id)
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.CALLED,
        staff_id=staff_member.staff_id,
    )
    await queue_service.transition_entry_status(
        queue_entry_id=entry.queue_entry_id,
        new_status=QueueEntryStatus.IN_PROGRESS,
        staff_id=staff_member.staff_id,
    )
    await queue_service.complete_queue_entry(
        queue_entry_id=entry.queue_entry_id,
        staff_id=staff_member.staff_id,
    )

    with pytest.raises(HTTPException) as exc:
        await queue_service.transition_entry_status(
            queue_entry_id=entry.queue_entry_id,
            new_status=QueueEntryStatus.CALLED,
            staff_id=staff_member.staff_id,
        )

    assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY