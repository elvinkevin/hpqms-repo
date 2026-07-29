import uuid
import pytest
from fastapi import HTTPException, status

from app.domain.models.models import (
    Department,
    Patient,
    QueueEntryStatus,
    QueuePriority,
    EntryType,
    RegistrationStatus,
    Visit,
    VisitStage,
)
from app.domain.services.routing_service import RoutingService


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
async def routing_service(db):
    """Provides a RoutingService instance bound to the active async session."""
    return RoutingService(db)


@pytest.fixture
async def patient(db):
    """Creates a fully registered active patient."""
    patient = Patient(
        first_name="Jane",
        last_name="Doe",
        registration_status=RegistrationStatus.COMPLETE,
    )
    db.add(patient)
    await db.flush()
    await db.refresh(patient)
    return patient


@pytest.fixture
async def incomplete_patient(db):
    """Creates a patient with an incomplete/skeleton registration profile."""
    patient = Patient(
        first_name="John",
        last_name="Doe",
        registration_status=RegistrationStatus.INCOMPLETE,
    )
    db.add(patient)
    await db.flush()
    await db.refresh(patient)
    return patient


@pytest.fixture
async def system_departments(db):
    """Seeds required system departments for kiosk dispatch and transfers."""
    depts = [
        Department(name="Reception", department_code="RECEPTION", is_active=True),
        Department(name="Triage", department_code="TRIAGE", is_active=True),
        Department(name="Emergency", department_code="EMERGENCY", is_active=True),
        Department(name="Radiology", department_code="RAD", is_active=True),
        Department(name="Closed Dept", department_code="CLOSED", is_active=False),
    ]
    db.add_all(depts)
    await db.flush()
    
    dept_map = {}
    for d in depts:
        await db.refresh(d)
        dept_map[d.department_code] = d
    return dept_map


@pytest.fixture
async def walkin_visit(db, patient):
    """Creates an active walk-in visit."""
    visit = Visit(
        patient_id=patient.patient_id,
        token_number="W-101",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.WALK_IN,
    )
    db.add(visit)
    await db.flush()
    await db.refresh(visit)
    return visit


# ==============================================================================
# GROUP 1: INITIAL KIOSK DISPATCH (6 TESTS)
# ==============================================================================

@pytest.mark.asyncio
async def test_dispatch_emergency_to_emergency(db, routing_service, patient, system_departments):
    """Emergency patients bypass triage/reception and enter Emergency with CRITICAL priority."""
    visit = Visit(
        patient_id=patient.patient_id,
        token_number="E-001",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.EMERGENCY,
    )
    db.add(visit)
    await db.flush()

    entry = await routing_service.dispatch_initial_kiosk_route(visit.visit_id)

    assert entry.department_id == system_departments["EMERGENCY"].dept_id
    assert entry.priority == QueuePriority.CRITICAL


@pytest.mark.asyncio
async def test_dispatch_incomplete_registration_to_reception(db, routing_service, incomplete_patient, system_departments):
    """Patients with incomplete profiles are routed to Reception regardless of entry type."""
    visit = Visit(
        patient_id=incomplete_patient.patient_id,
        token_number="A-101",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.APPOINTMENT,
    )
    db.add(visit)
    await db.flush()

    entry = await routing_service.dispatch_initial_kiosk_route(visit.visit_id)

    assert entry.department_id == system_departments["RECEPTION"].dept_id
    assert entry.priority == QueuePriority.NORMAL


@pytest.mark.asyncio
async def test_dispatch_appointment_to_triage(db, routing_service, patient, system_departments):
    """Fully registered appointment patients bypass Reception and go straight to Triage."""
    visit = Visit(
        patient_id=patient.patient_id,
        token_number="A-102",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.APPOINTMENT,
    )
    db.add(visit)
    await db.flush()

    entry = await routing_service.dispatch_initial_kiosk_route(visit.visit_id)

    assert entry.department_id == system_departments["TRIAGE"].dept_id


@pytest.mark.asyncio
async def test_dispatch_walkin_to_reception(routing_service, walkin_visit, system_departments):
    """Walk-in patients route directly to Reception."""
    entry = await routing_service.dispatch_initial_kiosk_route(walkin_visit.visit_id)

    assert entry.department_id == system_departments["RECEPTION"].dept_id


@pytest.mark.asyncio
async def test_dispatch_referral_to_reception(db, routing_service, patient, system_departments):
    """Referred patients route directly to Reception."""
    visit = Visit(
        patient_id=patient.patient_id,
        token_number="R-201",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.REFERRAL,
    )
    db.add(visit)
    await db.flush()

    entry = await routing_service.dispatch_initial_kiosk_route(visit.visit_id)

    assert entry.department_id == system_departments["RECEPTION"].dept_id


@pytest.mark.asyncio
async def test_dispatch_unknown_visit_raises_404(routing_service):
    """Routing an invalid visit UUID raises HTTP 404."""
    with pytest.raises(HTTPException) as exc:
        await routing_service.dispatch_initial_kiosk_route(uuid.uuid4())

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# GROUP 2: PATIENT TRANSFERS (5 TESTS)
# ==============================================================================

@pytest.mark.asyncio
async def test_move_patient_success(routing_service, walkin_visit, system_departments):
    """Verifies moving a patient creates a new active queue entry in the target department."""
    target_dept = system_departments["TRIAGE"]

    entry = await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=target_dept.dept_id,
        priority=QueuePriority.NORMAL,
        notes="Routing from kiosk to triage",
    )

    assert entry.department_id == target_dept.dept_id
    assert entry.visit_id == walkin_visit.visit_id
    assert entry.status == QueueEntryStatus.WAITING


@pytest.mark.asyncio
async def test_move_patient_completes_existing_queue(
    routing_service,
    walkin_visit,
    system_departments,
):
    reception = system_departments["RECEPTION"]
    triage = system_departments["TRIAGE"]

    # Patient enters Reception queue
    initial_entry = await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=reception.dept_id,
    )

    # Reception begins serving the patient
    await routing_service.queue_service.call_queue_entry(
        initial_entry.queue_entry_id
    )

    await routing_service.queue_service.start_consultation(
        initial_entry.queue_entry_id
    )

    # Reception transfers patient to Triage
    next_entry = await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=triage.dept_id,
    )

    completed_entry = await routing_service.queue_service.get_queue_entry(
        initial_entry.queue_entry_id
    )

    assert completed_entry.status == QueueEntryStatus.COMPLETED
    assert "Transferred" in completed_entry.notes
    assert next_entry.queue_entry_id != initial_entry.queue_entry_id


@pytest.mark.asyncio
async def test_move_patient_updates_visit_current_queue(routing_service, walkin_visit, system_departments):
    """Verifies that Visit.current_queue_entry_id is updated upon transfer."""
    triage = system_departments["TRIAGE"]

    entry = await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=triage.dept_id,
    )

    updated_visit = await routing_service.visit_service.get_visit(walkin_visit.visit_id)
    assert updated_visit.current_queue_entry_id == entry.queue_entry_id


@pytest.mark.asyncio
async def test_move_patient_inactive_visit_rejected(db, routing_service, patient, system_departments):
    """Transfers fail with HTTP 409 Conflict if the visit is no longer active (e.g., DISCHARGED)."""
    closed_visit = Visit(
        patient_id=patient.patient_id,
        token_number="W-999",
        stage=VisitStage.COMPLETED,
        entry_type=EntryType.WALK_IN,
    )
    db.add(closed_visit)
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await routing_service.move_patient(
            visit_id=closed_visit.visit_id,
            target_department_id=system_departments["TRIAGE"].dept_id,
        )

    assert exc.value.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_move_patient_inactive_department_rejected(routing_service, walkin_visit, system_departments):
    """Transfers fail with HTTP 400 Bad Request if the target department is marked inactive."""
    closed_dept = system_departments["CLOSED"]

    with pytest.raises(HTTPException) as exc:
        await routing_service.move_patient(
            visit_id=walkin_visit.visit_id,
            target_department_id=closed_dept.dept_id,
        )

    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# GROUP 3: CURRENT LOCATION (2 TESTS)
# ==============================================================================

@pytest.mark.asyncio
async def test_get_current_location_active_queue(routing_service, walkin_visit, system_departments):
    """Location query returns accurate department name, position, wait time, and queue status."""
    reception = system_departments["RECEPTION"]
    
    await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=reception.dept_id,
    )

    loc = await routing_service.get_current_location(walkin_visit.visit_id)

    assert loc["visit_id"] == walkin_visit.visit_id
    assert loc["department"] == "Reception"
    assert loc["department_id"] == reception.dept_id
    assert loc["queue_status"] == "WAITING"
    assert loc["position"] == 1


@pytest.mark.asyncio
async def test_get_current_location_no_active_queue(routing_service, walkin_visit):
    """Location query returns neutral empty metrics if the visit has no active ticket."""
    loc = await routing_service.get_current_location(walkin_visit.visit_id)

    assert loc["visit_id"] == walkin_visit.visit_id
    assert loc["department"] is None
    assert loc["queue_status"] is None
    assert loc["position"] == 0
    assert loc["estimated_wait"] == 0


# ==============================================================================
# GROUP 4: MOVEMENT HISTORY (2 TESTS)
# ==============================================================================

@pytest.mark.asyncio
async def test_get_token_movement_history_ordered(
    routing_service,
    walkin_visit,
    system_departments,
):
    reception = system_departments["RECEPTION"]
    triage = system_departments["TRIAGE"]

    e1 = await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=reception.dept_id,
    )

    await routing_service.queue_service.call_queue_entry(
        e1.queue_entry_id
    )

    await routing_service.queue_service.start_consultation(
        e1.queue_entry_id
    )

    e2 = await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=triage.dept_id,
    )

    history = await routing_service.get_token_movement_history(
        walkin_visit.visit_id
    )

    assert len(history) == 2

    assert history[0].queue_entry_id == e1.queue_entry_id
    assert history[1].queue_entry_id == e2.queue_entry_id

    assert history[0].department.name == "Reception"
    assert history[1].department.name == "Triage"


@pytest.mark.asyncio
async def test_get_token_movement_history_empty(routing_service, walkin_visit):
    """Movement history returns an empty list for a visit that has not been queued anywhere."""
    history = await routing_service.get_token_movement_history(walkin_visit.visit_id)
    assert history == []

@pytest.mark.asyncio
async def test_cannot_transfer_waiting_patient(
    routing_service,
    walkin_visit,
    system_departments,
):
    reception = system_departments["RECEPTION"]
    triage = system_departments["TRIAGE"]

    await routing_service.move_patient(
        visit_id=walkin_visit.visit_id,
        target_department_id=reception.dept_id,
    )

    with pytest.raises(HTTPException) as exc:
        await routing_service.move_patient(
            visit_id=walkin_visit.visit_id,
            target_department_id=triage.dept_id,
        )

    assert exc.value.status_code == status.HTTP_409_CONFLICT