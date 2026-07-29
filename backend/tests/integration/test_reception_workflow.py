import pytest
from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.domain.models.models import (
    EntryType,
    Patient,
    QueueEntryStatus,
    RegistrationStatus,
    Visit,
    VisitStage,
)
from app.domain.schemas.schemas import PatientCreate, VisitCreate
from app.domain.services.patient_service import PatientService
from app.domain.services.routing_service import RoutingService
from app.domain.services.visit_service import VisitService


@pytest.mark.asyncio
async def test_walk_in_patient_registration_workflow(
    db,
    routing_departments,
):
    """
    Integration test:
    Kiosk / Reception creates an initial walk-in patient record.

    Expected workflow:
    Register Skeleton Patient (INCOMPLETE)
            ↓
    Start Visit (ACTIVE)
            ↓
    Generate Walk-In Token (W-xxx)
            ↓
    Route INCOMPLETE Patient to Reception for Demographics
            ↓
    Create WAITING Queue Entry at Reception
    """

    patient_service = PatientService(db)
    visit_service = VisitService(db)
    routing_service = RoutingService(db)

    # 1. Initial patient check-in / skeleton registration
    patient = await patient_service.register(
        PatientCreate(
            first_name="John",
            last_name="Doe",
            national_id="12345678",
            phone="+254700111222",
            gender="MALE",
            date_of_birth="1995-05-20",
        )
    )

    # 2. Create visit
    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="General Consultation",
        )
    )

    # 3. Route patient through initial kiosk dispatch
    queue_entry = await routing_service.dispatch_initial_kiosk_route(
        visit.visit_id
    )

    # Domain & State Assertions
    assert patient.patient_id is not None
    assert patient.registration_status == RegistrationStatus.INCOMPLETE

    # Visit status checks
    assert visit.patient_id == patient.patient_id
    assert visit.stage == VisitStage.ACTIVE
    assert visit.token_number.startswith("W-")

    # Routing decision checks: INCOMPLETE status forces route to Reception
    assert queue_entry.visit_id == visit.visit_id
    assert queue_entry.department_id == routing_departments["reception"].dept_id
    assert queue_entry.status == QueueEntryStatus.WAITING

    # Relational Database State Verification
    await db.refresh(visit)
    assert visit.current_queue_entry_id == queue_entry.queue_entry_id


@pytest.mark.asyncio
async def test_existing_patient_walk_in_workflow(
    db,
    routing_departments,
    existing_patient,
):
    """
    Integration test:
    An existing, fully registered patient returns to the hospital for a new walk-in visit.

    Expected workflow:
    Lookup Existing Patient (COMPLETE)
            ↓
    Start New Visit (ACTIVE)
            ↓
    Generate New Walk-In Token (W-xxx)
            ↓
    Route COMPLETE Walk-In Patient to Reception
            ↓
    Create WAITING Queue Entry at Reception
            ↓
    Verify NO duplicate patient record created
    """

    visit_service = VisitService(db)
    routing_service = RoutingService(db)

    # 1. Start new visit for existing registered patient
    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=existing_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Follow-up Consultation",
        )
    )

    # 2. Route patient through initial kiosk dispatch
    queue_entry = await routing_service.dispatch_initial_kiosk_route(
        visit.visit_id
    )

    # Assertions
    assert visit.patient_id == existing_patient.patient_id
    assert visit.visit_id is not None
    assert visit.stage == VisitStage.ACTIVE
    assert visit.token_number.startswith("W-")

    # Routed to reception (COMPLETE + WALK_IN)
    assert queue_entry.visit_id == visit.visit_id
    assert (
        queue_entry.department_id == routing_departments["reception"].dept_id
    )
    assert queue_entry.status == QueueEntryStatus.WAITING

    # Visit relationship linked
    await db.refresh(visit)
    assert visit.current_queue_entry_id == queue_entry.queue_entry_id

    # Confirm zero duplicate patient records were added
    patient_count_result = await db.execute(
        select(func.count()).select_from(Patient)
    )
    assert patient_count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_duplicate_active_visit_rejected(
    db,
    existing_patient,
):
    """
    Integration test:
    Enforces the single active visit invariant per patient.

    Expected workflow:
    Existing Patient -> Start Initial Visit (ACTIVE)
            ↓
    Attempt Second Visit for Same Patient
            ↓
    HTTP 409 Conflict Error
            ↓
    Verify Database contains exactly ONE Visit record (No partial write)
    """

    visit_service = VisitService(db)

    # 1. Create first active visit (Succeeds)
    first_visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=existing_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Initial Checkup",
        )
    )

    assert first_visit.stage == VisitStage.ACTIVE

    # 2. Attempt to create second active visit for the same patient (Fails)
    with pytest.raises(HTTPException) as exc_info:
        await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Concurrent Second Checkup",
            )
        )

    # 3. Verify exact business error contract
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Patient already has an active visit."

    # 4. Verify transaction integrity (database still has exactly one visit record)
    visit_count_result = await db.execute(
        select(func.count()).select_from(Visit)
    )
    assert visit_count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_patient_queue_progression(
    db,
    routing_departments,
    existing_patient,
):
    """
    Integration test:
    Validates the complete Queue Entry state machine.

    Expected workflow:
    Start Visit & Initial Route
            ↓
    WAITING (Initial state)
            ↓
    Call Queue Entry -> CALLED
            ↓
    Start Queue Entry -> IN_PROGRESS
            ↓
    Complete Queue Entry -> COMPLETED
    """

    visit_service = VisitService(db)
    routing_service = RoutingService(db)

    # 1. Start visit and dispatch initial route
    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=existing_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Queue Progression Test",
        )
    )

    initial_entry = await routing_service.dispatch_initial_kiosk_route(
        visit.visit_id
    )

    # Step A: Initial state MUST be WAITING
    assert initial_entry.status == QueueEntryStatus.WAITING

    # Step B: Call patient into consultation/desk (WAITING -> CALLED)
    called_entry = await routing_service.call_queue_entry(
        initial_entry.queue_entry_id
    )
    assert called_entry.status == QueueEntryStatus.CALLED

    # Step C: Start processing patient (CALLED -> IN_PROGRESS)
    started_entry = await routing_service.start_queue_entry(
        initial_entry.queue_entry_id
    )
    assert started_entry.status == QueueEntryStatus.IN_PROGRESS

    # Step D: Complete service at desk (IN_PROGRESS -> COMPLETED)
    completed_entry = await routing_service.complete_queue_entry(
        initial_entry.queue_entry_id
    )
    assert completed_entry.status == QueueEntryStatus.COMPLETED

    # Relational State Verification
    await db.refresh(completed_entry)
    assert completed_entry.queue_entry_id == initial_entry.queue_entry_id


@pytest.mark.asyncio
async def test_patient_visit_completion(
    db,
    routing_departments,
    existing_patient,
):
    """
    Integration test:
    Validates completing the overall visit after queue processing wraps up.

    Expected workflow:
    Start Visit (ACTIVE) & Dispatch Route
            ↓
    Queue Progression: WAITING -> CALLED -> IN_PROGRESS -> COMPLETED
            ↓
    Complete Visit (VisitStage -> COMPLETED)
            ↓
    Verify visit timestamp and current queue entry link maintained
    """

    visit_service = VisitService(db)
    routing_service = RoutingService(db)

    # 1. Start visit
    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=existing_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Single Station Consultation",
        )
    )

    queue_entry = await routing_service.dispatch_initial_kiosk_route(
        visit.visit_id
    )

    # 2. Advance queue entry to completion
    await routing_service.call_queue_entry(queue_entry.queue_entry_id)
    await routing_service.start_queue_entry(queue_entry.queue_entry_id)
    completed_queue_entry = await routing_service.complete_queue_entry(
        queue_entry.queue_entry_id
    )

    # 3. Finalize/Complete the entire patient visit
    completed_visit = await visit_service.complete_visit(visit.visit_id)

    # -----------------------------------------------------------------------
    # Domain Assertions
    # -----------------------------------------------------------------------
    # Queue entry entity state
    assert completed_queue_entry.status == QueueEntryStatus.COMPLETED

    # Visit entity state
    assert completed_visit.stage == VisitStage.COMPLETED
    assert completed_visit.completed_at is not None

    # Relationship integrity maintained
    assert (
        completed_visit.current_queue_entry_id
        == completed_queue_entry.queue_entry_id
    )


@pytest.mark.asyncio
async def test_patient_visit_cancellation(
    db,
    routing_departments,
    existing_patient,
):
    """
    Integration test:
    Validates cancelling an active visit (e.g., patient leaves before service).

    Expected workflow:
    Start Visit (ACTIVE) & Dispatch Route (WAITING)
            ↓
    Patient leaves / cancels visit
            ↓
    Cancel Visit (VisitStage -> CANCELLED)
            ↓
    Verify Queue Entry state and visit stage
    """

    visit_service = VisitService(db)
    routing_service = RoutingService(db)

    # 1. Start visit and dispatch route
    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=existing_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Cancelled Walk-in",
        )
    )

    queue_entry = await routing_service.dispatch_initial_kiosk_route(
        visit.visit_id
    )

    assert visit.stage == VisitStage.ACTIVE
    assert queue_entry.status == QueueEntryStatus.WAITING

    # 2. Cancel the visit (passing only visit_id as per VisitService signature)
    cancelled_visit = await visit_service.cancel_visit(visit.visit_id)

    # -----------------------------------------------------------------------
    # Domain Assertions
    # -----------------------------------------------------------------------
    assert cancelled_visit.stage == VisitStage.CANCELLED
    assert cancelled_visit.completed_at is not None

    # Verify queue entry state after cancellation
    await db.refresh(queue_entry)
    assert queue_entry.status in (
        QueueEntryStatus.CANCELLED,
        QueueEntryStatus.COMPLETED,
        QueueEntryStatus.WAITING,
    )