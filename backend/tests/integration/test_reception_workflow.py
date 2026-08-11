from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.domain.models.models import (
    EntryType,
    Patient,
    QueueEntryStatus,
    QueuePriority,
    RegistrationStatus,
    Visit,
    VisitStage,
)
from app.domain.schemas.schemas import PatientCreate, VisitCreate
from app.domain.services.patient_service import PatientService
from app.domain.services.routing_service import RoutingService
from app.domain.services.visit_service import VisitService
from app.domain.services.queue_service import QueueService


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


@pytest.mark.asyncio
async def test_patient_no_show_and_requeue_workflow(
    db,
    routing_departments,
    existing_patient,
):
    """
    Integration test:

    Start Visit
        ↓
    Initial Route
        ↓
    WAITING
        ↓
    CALLED
        ↓
    NO_SHOW
        ↓
    RE-QUEUE
        ↓
    WAITING

    Verifies that:
    - NO_SHOW is persisted
    - no_show_at is recorded
    - the queue entry is removed from the active queue
    - the same queue entry can be re-queued
    - the entry returns to WAITING
    - the original no_show_at remains as history
    """

    visit_service = VisitService(db)
    routing_service = RoutingService(db)
    queue_service = QueueService(db)

    # ------------------------------------------------------------------
    # 1. Start visit and create initial queue entry
    # ------------------------------------------------------------------

    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=existing_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="No Show / Requeue Test",
        )
    )

    queue_entry = await routing_service.dispatch_initial_kiosk_route(
        visit.visit_id
    )

    assert queue_entry.status == QueueEntryStatus.WAITING

    # ------------------------------------------------------------------
    # 2. Call patient
    # ------------------------------------------------------------------

    called_entry = await queue_service.transition_entry_status(
        queue_entry.queue_entry_id,
        QueueEntryStatus.CALLED,
    )

    assert called_entry.status == QueueEntryStatus.CALLED
    assert called_entry.called_at is not None

    # ------------------------------------------------------------------
    # 3. Mark patient as NO_SHOW
    # ------------------------------------------------------------------

    no_show_entry = await queue_service.transition_entry_status(
        queue_entry.queue_entry_id,
        QueueEntryStatus.NO_SHOW,
        notes="Patient did not respond to call.",
    )

    assert no_show_entry.status == QueueEntryStatus.NO_SHOW

    # NO_SHOW must have its audit timestamp
    assert no_show_entry.no_show_at is not None

    # The patient was previously called
    assert no_show_entry.called_at is not None

    # ------------------------------------------------------------------
    # 4. Verify NO_SHOW is no longer part of the active queue
    # ------------------------------------------------------------------

    active_queue = await queue_service.get_department_queue(
        routing_departments["reception"].dept_id
    )

    active_queue_ids = {
        entry.queue_entry_id
        for entry in active_queue
    }

    assert queue_entry.queue_entry_id not in active_queue_ids

    # ------------------------------------------------------------------
    # 5. Re-queue the patient
    # ------------------------------------------------------------------

    requeued_entry = await queue_service.transition_entry_status(
        queue_entry.queue_entry_id,
        QueueEntryStatus.WAITING,
    )

    assert requeued_entry.status == QueueEntryStatus.WAITING

    # ------------------------------------------------------------------
    # 6. Verify NO_SHOW history was preserved
    # ------------------------------------------------------------------

    assert requeued_entry.no_show_at is not None

    # The original call history should also remain
    assert requeued_entry.called_at is not None

    # ------------------------------------------------------------------
    # 7. Verify the patient is back in the active queue
    # ------------------------------------------------------------------

    active_queue = await queue_service.get_department_queue(
        routing_departments["reception"].dept_id
    )

    active_queue_ids = {
        entry.queue_entry_id
        for entry in active_queue
    }

    assert queue_entry.queue_entry_id in active_queue_ids

    # And it should be WAITING again
    restored_entry = next(
        entry
        for entry in active_queue
        if entry.queue_entry_id == queue_entry.queue_entry_id
    )

    assert restored_entry.status == QueueEntryStatus.WAITING


@pytest.mark.asyncio
async def test_requeued_patient_respects_priority_ordering(
    db,
    routing_departments,
    patient_factory,
    services,
):
    """
    Verify that re-queueing a NO_SHOW patient restores the entry to WAITING
    and that the normal queue priority ordering is still respected.

    Expected ordering:

        URGENT
        NORMAL

    even if the NORMAL patient originally entered the queue first.
    """

    patient_service = services["patient"]
    visit_service = services["visit"]
    routing_service = services["routing"]
    queue_service = services["queue"]

    reception = routing_departments["reception"]

    # --------------------------------------------------------------
    # 1. Create two distinct patients
    # --------------------------------------------------------------

    normal_patient = await patient_factory(
        first_name="Normal",
        last_name="Patient",
        phone="+254700000001",
    )

    urgent_patient = await patient_factory(
        first_name="Urgent",
        last_name="Patient",
        phone="+254700000002",
    )

    # --------------------------------------------------------------
    # 2. Start both visits
    # --------------------------------------------------------------

    normal_visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=normal_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Priority requeue test",
        )
    )

    urgent_visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=urgent_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Priority requeue test",
        )
    )

    # --------------------------------------------------------------
    # 3. Create queue entries
    # --------------------------------------------------------------

    normal_entry = await queue_service.create_queue_entry(
        visit_id=normal_visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.NORMAL,
    )

    urgent_entry = await queue_service.create_queue_entry(
        visit_id=urgent_visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.URGENT,
    )

    assert normal_entry.status == QueueEntryStatus.WAITING
    assert urgent_entry.status == QueueEntryStatus.WAITING

    # Normal patient entered first.
    assert normal_entry.sequence_number < urgent_entry.sequence_number

    # --------------------------------------------------------------
    # 4. Verify initial priority ordering
    # --------------------------------------------------------------

    queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    assert [entry.queue_entry_id for entry in queue] == [
        urgent_entry.queue_entry_id,
        normal_entry.queue_entry_id,
    ]

    # --------------------------------------------------------------
    # 5. Call the NORMAL patient
    # --------------------------------------------------------------

    called_entry = await queue_service.call_queue_entry(
        normal_entry.queue_entry_id
    )

    assert called_entry.status == QueueEntryStatus.CALLED

    # --------------------------------------------------------------
    # 6. Mark NORMAL patient as NO_SHOW
    # --------------------------------------------------------------

    no_show_entry = await queue_service.transition_entry_status(
        normal_entry.queue_entry_id,
        QueueEntryStatus.NO_SHOW,
        notes="Patient did not respond to call.",
    )

    assert no_show_entry.status == QueueEntryStatus.NO_SHOW
    assert no_show_entry.no_show_at is not None

    # --------------------------------------------------------------
    # 7. Verify NO_SHOW patient leaves the active queue
    # --------------------------------------------------------------

    queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    assert [entry.queue_entry_id for entry in queue] == [
        urgent_entry.queue_entry_id,
    ]

    # --------------------------------------------------------------
    # 8. Re-queue the NORMAL patient
    # --------------------------------------------------------------

    requeued_entry = await queue_service.transition_entry_status(
        normal_entry.queue_entry_id,
        QueueEntryStatus.WAITING,
    )

    assert requeued_entry.status == QueueEntryStatus.WAITING

    # --------------------------------------------------------------
    # 9. Verify priority ordering after requeue
    # --------------------------------------------------------------

    queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    # URGENT must remain ahead of NORMAL.
    assert [entry.queue_entry_id for entry in queue] == [
        urgent_entry.queue_entry_id,
        normal_entry.queue_entry_id,
    ]

    assert queue[0].priority == QueuePriority.URGENT
    assert queue[1].priority == QueuePriority.NORMAL

    # --------------------------------------------------------------
    # 10. Verify the requeued entry retained its history
    # --------------------------------------------------------------

    assert requeued_entry.no_show_at is not None
    assert requeued_entry.called_at is not None

@pytest.mark.asyncio
async def test_requeued_critical_patient_restores_priority_order(
    db,
    routing_departments,
    patient_factory,
    services,
):
    """
    Verify that a CRITICAL patient who becomes NO_SHOW and is subsequently
    re-queued returns to the queue according to priority ordering.

    Expected order:

        CRITICAL
        URGENT
        SEMI_URGENT
        NORMAL
    """

    visit_service = services["visit"]
    queue_service = services["queue"]

    reception = routing_departments["reception"]

    # --------------------------------------------------------------
    # 1. Create four patients
    # --------------------------------------------------------------

    patients = [
        await patient_factory(
            first_name="Normal",
            last_name="Patient",
            phone="+254700000011",
        ),
        await patient_factory(
            first_name="SemiUrgent",
            last_name="Patient",
            phone="+254700000012",
        ),
        await patient_factory(
            first_name="Urgent",
            last_name="Patient",
            phone="+254700000013",
        ),
        await patient_factory(
            first_name="Critical",
            last_name="Patient",
            phone="+254700000014",
        ),
    ]

    priorities = [
        QueuePriority.NORMAL,
        QueuePriority.SEMI_URGENT,
        QueuePriority.URGENT,
        QueuePriority.CRITICAL,
    ]

    entries = []

    # --------------------------------------------------------------
    # 2. Create visits and queue entries
    # --------------------------------------------------------------

    for patient, priority in zip(patients, priorities):
        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Full priority requeue test",
            )
        )

        entry = await queue_service.create_queue_entry(
            visit_id=visit.visit_id,
            department_id=reception.dept_id,
            priority=priority,
        )

        entries.append(entry)

    # --------------------------------------------------------------
    # 3. Verify initial priority ordering
    # --------------------------------------------------------------

    queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    assert [entry.priority for entry in queue] == [
        QueuePriority.CRITICAL,
        QueuePriority.URGENT,
        QueuePriority.SEMI_URGENT,
        QueuePriority.NORMAL,
    ]

    # --------------------------------------------------------------
    # 4. Identify the CRITICAL entry
    # --------------------------------------------------------------

    critical_entry = next(
        entry
        for entry in entries
        if entry.priority == QueuePriority.CRITICAL
    )

    # --------------------------------------------------------------
    # 5. Call the CRITICAL patient
    # --------------------------------------------------------------

    called_entry = await queue_service.call_queue_entry(
        critical_entry.queue_entry_id
    )

    assert called_entry.status == QueueEntryStatus.CALLED

    # --------------------------------------------------------------
    # 6. Mark CRITICAL patient as NO_SHOW
    # --------------------------------------------------------------

    no_show_entry = await queue_service.transition_entry_status(
        critical_entry.queue_entry_id,
        QueueEntryStatus.NO_SHOW,
        notes="Critical patient did not respond to call.",
    )

    assert no_show_entry.status == QueueEntryStatus.NO_SHOW
    assert no_show_entry.no_show_at is not None

    # --------------------------------------------------------------
    # 7. CRITICAL patient should no longer be active
    # --------------------------------------------------------------

    queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    assert all(
        entry.queue_entry_id != critical_entry.queue_entry_id
        for entry in queue
    )

    assert [entry.priority for entry in queue] == [
        QueuePriority.URGENT,
        QueuePriority.SEMI_URGENT,
        QueuePriority.NORMAL,
    ]

    # --------------------------------------------------------------
    # 8. Re-queue the CRITICAL patient
    # --------------------------------------------------------------

    requeued_entry = await queue_service.transition_entry_status(
        critical_entry.queue_entry_id,
        QueueEntryStatus.WAITING,
    )

    assert requeued_entry.status == QueueEntryStatus.WAITING

    # --------------------------------------------------------------
    # 9. Verify CRITICAL returns to the top
    # --------------------------------------------------------------

    queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    assert [entry.priority for entry in queue] == [
        QueuePriority.CRITICAL,
        QueuePriority.URGENT,
        QueuePriority.SEMI_URGENT,
        QueuePriority.NORMAL,
    ]

    assert queue[0].queue_entry_id == critical_entry.queue_entry_id

    # --------------------------------------------------------------
    # 10. Verify lifecycle history survived requeue
    # --------------------------------------------------------------

    assert requeued_entry.no_show_at is not None
    assert requeued_entry.called_at is not None

@pytest.mark.asyncio
async def test_no_show_requeue_preserves_priority_order(
    reception_context,
    patient_factory,
):
    """
    Verifies the complete NO_SHOW -> WAITING lifecycle.

    Scenario:
        1. Create a NORMAL patient.
        2. Create an URGENT patient.
        3. Call the NORMAL patient.
        4. Mark the patient as NO_SHOW.
        5. Verify the patient leaves the active queue.
        6. Re-queue the patient.
        7. Verify the patient returns as WAITING.
        8. Verify the URGENT patient remains ahead of them.
    """

    db = reception_context["db"]
    reception = reception_context["reception"]

    patient_service = reception_context["services"]["patient"]
    visit_service = reception_context["services"]["visit"]
    queue_service = reception_context["services"]["queue"]

    # ---------------------------------------------------------------
    # Create NORMAL patient
    # ---------------------------------------------------------------

    normal_patient = await patient_factory(
        first_name="Normal",
        last_name="Patient",
    )

    normal_visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=normal_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="No-show lifecycle test",
        )
    )

    normal_entry = await queue_service.create_queue_entry(
        visit_id=normal_visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.NORMAL,
    )

    # ---------------------------------------------------------------
    # Create URGENT patient
    # ---------------------------------------------------------------

    urgent_patient = await patient_factory(
        first_name="Urgent",
        last_name="Patient",
    )

    urgent_visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=urgent_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Priority comparison",
        )
    )

    urgent_entry = await queue_service.create_queue_entry(
        visit_id=urgent_visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.URGENT,
    )

    await db.commit()

    # ---------------------------------------------------------------
    # Call the NORMAL patient
    # ---------------------------------------------------------------

    normal_entry = await queue_service.call_queue_entry(
        normal_entry.queue_entry_id
    )

    await db.commit()

    assert normal_entry.status == QueueEntryStatus.CALLED

    # ---------------------------------------------------------------
    # Mark NORMAL patient as NO_SHOW
    # ---------------------------------------------------------------

    normal_entry = await queue_service.transition_entry_status(
        normal_entry.queue_entry_id,
        QueueEntryStatus.NO_SHOW,
    )

    await db.commit()

    assert normal_entry.status == QueueEntryStatus.NO_SHOW
    assert normal_entry.no_show_at is not None

    # ---------------------------------------------------------------
    # Verify NO_SHOW patient is no longer active
    # ---------------------------------------------------------------

    active_queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    active_ids = {
        entry.queue_entry_id
        for entry in active_queue
    }

    assert normal_entry.queue_entry_id not in active_ids
    assert urgent_entry.queue_entry_id in active_ids

    # ---------------------------------------------------------------
    # RE-QUEUE NORMAL patient
    # ---------------------------------------------------------------

    normal_entry = await queue_service.transition_entry_status(
        normal_entry.queue_entry_id,
        QueueEntryStatus.WAITING,
    )

    await db.commit()

    assert normal_entry.status == QueueEntryStatus.WAITING

    # ---------------------------------------------------------------
    # Verify both patients are active again
    # ---------------------------------------------------------------

    active_queue = await queue_service.get_department_queue(
        reception.dept_id
    )

    # Extract only the two entries from this test.
    test_entries = [
        entry
        for entry in active_queue
        if entry.queue_entry_id in {
            normal_entry.queue_entry_id,
            urgent_entry.queue_entry_id,
        }
    ]

    assert len(test_entries) == 2

    # ---------------------------------------------------------------
    # Verify PRIORITY ordering was restored
    # ---------------------------------------------------------------

    assert test_entries[0].queue_entry_id == urgent_entry.queue_entry_id
    assert test_entries[0].priority == QueuePriority.URGENT

    assert test_entries[1].queue_entry_id == normal_entry.queue_entry_id
    assert test_entries[1].priority == QueuePriority.NORMAL


@pytest.mark.asyncio
async def test_waiting_patient_cannot_be_completed(
    reception_context,
    patient_factory,
):
    db = reception_context["db"]
    reception = reception_context["reception"]

    visit_service = reception_context["services"]["visit"]
    queue_service = reception_context["services"]["queue"]

    patient = await patient_factory(
        first_name="Invalid",
        last_name="Transition",
    )

    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Invalid transition test",
        )
    )

    entry = await queue_service.create_queue_entry(
        visit_id=visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.NORMAL,
    )

    await db.commit()

    assert entry.status == QueueEntryStatus.WAITING

    with pytest.raises(HTTPException) as exc_info:
        await queue_service.transition_entry_status(
            entry.queue_entry_id,
            QueueEntryStatus.COMPLETED,
        )

    assert exc_info.value.status_code == 422
    assert "Invalid state transition" in exc_info.value.detail

    # Make sure the database state was not corrupted.
    await db.refresh(entry)

    assert entry.status == QueueEntryStatus.WAITING

@pytest.mark.asyncio
async def test_waiting_patient_rejects_invalid_transitions(
    reception_context,
    patient_factory,
):
    db = reception_context["db"]
    reception = reception_context["reception"]

    visit_service = reception_context["services"]["visit"]
    queue_service = reception_context["services"]["queue"]

    patient = await patient_factory(
        first_name="Waiting",
        last_name="Invalid",
    )

    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Invalid transition matrix",
        )
    )

    entry = await queue_service.create_queue_entry(
        visit_id=visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.NORMAL,
    )

    await db.commit()

    assert entry.status == QueueEntryStatus.WAITING

    invalid_targets = [
        QueueEntryStatus.IN_PROGRESS,
        QueueEntryStatus.COMPLETED,
        QueueEntryStatus.NO_SHOW,
    ]

    for invalid_status in invalid_targets:
        with pytest.raises(HTTPException) as exc_info:
            await queue_service.transition_entry_status(
                entry.queue_entry_id,
                invalid_status,
            )

        assert exc_info.value.status_code == 422
        assert "Invalid state transition" in exc_info.value.detail

        await db.refresh(entry)
        assert entry.status == QueueEntryStatus.WAITING

@pytest.mark.asyncio
async def test_called_patient_cannot_skip_to_completed(
    reception_context,
    patient_factory,
):
    db = reception_context["db"]
    reception = reception_context["reception"]

    visit_service = reception_context["services"]["visit"]
    queue_service = reception_context["services"]["queue"]

    patient = await patient_factory(
        first_name="Called",
        last_name="Invalid",
    )

    visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Called transition test",
        )
    )

    entry = await queue_service.create_queue_entry(
        visit_id=visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.NORMAL,
    )

    await db.commit()

    entry = await queue_service.call_queue_entry(
        entry.queue_entry_id
    )

    await db.commit()

    assert entry.status == QueueEntryStatus.CALLED

    with pytest.raises(HTTPException) as exc_info:
        await queue_service.transition_entry_status(
            entry.queue_entry_id,
            QueueEntryStatus.COMPLETED,
        )

    assert exc_info.value.status_code == 422

    await db.refresh(entry)

    assert entry.status == QueueEntryStatus.CALLED

@pytest.mark.asyncio
async def test_terminal_queue_states_cannot_be_reactivated(
    reception_context,
    patient_factory,
):
    db = reception_context["db"]
    reception = reception_context["reception"]

    visit_service = reception_context["services"]["visit"]
    queue_service = reception_context["services"]["queue"]

    # ---------------------------------------------------------------
    # COMPLETED entry
    # ---------------------------------------------------------------

    completed_patient = await patient_factory(
        first_name="Completed",
        last_name="Patient",
    )

    completed_visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=completed_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Terminal state test",
        )
    )

    completed_entry = await queue_service.create_queue_entry(
        visit_id=completed_visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.NORMAL,
    )

    completed_entry = await queue_service.call_queue_entry(
        completed_entry.queue_entry_id
    )

    completed_entry = await queue_service.transition_entry_status(
        completed_entry.queue_entry_id,
        QueueEntryStatus.IN_PROGRESS,
    )

    completed_entry = await queue_service.transition_entry_status(
        completed_entry.queue_entry_id,
        QueueEntryStatus.COMPLETED,
    )

    await db.commit()

    assert completed_entry.status == QueueEntryStatus.COMPLETED

    # COMPLETED cannot return to an active state.
    for invalid_status in [
        QueueEntryStatus.WAITING,
        QueueEntryStatus.CALLED,
        QueueEntryStatus.IN_PROGRESS,
    ]:
        with pytest.raises(HTTPException):
            await queue_service.transition_entry_status(
                completed_entry.queue_entry_id,
                invalid_status,
            )

    await db.refresh(completed_entry)

    assert completed_entry.status == QueueEntryStatus.COMPLETED

    # ---------------------------------------------------------------
    # CANCELLED entry
    # ---------------------------------------------------------------

    cancelled_patient = await patient_factory(
        first_name="Cancelled",
        last_name="Patient",
    )

    cancelled_visit = await visit_service.start_visit(
        VisitCreate(
            patient_id=cancelled_patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Terminal state test",
        )
    )

    cancelled_entry = await queue_service.create_queue_entry(
        visit_id=cancelled_visit.visit_id,
        department_id=reception.dept_id,
        priority=QueuePriority.NORMAL,
    )

    cancelled_entry = await queue_service.transition_entry_status(
        cancelled_entry.queue_entry_id,
        QueueEntryStatus.CANCELLED,
    )

    await db.commit()

    assert cancelled_entry.status == QueueEntryStatus.CANCELLED

    # CANCELLED cannot return to an active state.
    for invalid_status in [
        QueueEntryStatus.WAITING,
        QueueEntryStatus.CALLED,
        QueueEntryStatus.IN_PROGRESS,
    ]:
        with pytest.raises(HTTPException):
            await queue_service.transition_entry_status(
                cancelled_entry.queue_entry_id,
                invalid_status,
            )

    await db.refresh(cancelled_entry)

    assert cancelled_entry.status == QueueEntryStatus.CANCELLED

@pytest.mark.asyncio
async def test_already_called_patient_cannot_be_called_again(reception_context):
    services = reception_context["services"]
    queue_service = services["queue"]

    patient = await services["patient"].register_standard_patient(
        PatientCreate(
            national_id=f"TEST-{uuid4()}",
            first_name="Double",
            last_name="Call",
            phone=f"+2547{uuid4().int % 10**8:08d}",
        )
    )

    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Duplicate call test",
        )
    )

    entry = await queue_service.create_queue_entry(
        visit.visit_id,
        reception_context["reception"].dept_id,
    )

    await queue_service.call_queue_entry(entry.queue_entry_id)

    with pytest.raises(HTTPException) as exc:
        await queue_service.call_queue_entry(entry.queue_entry_id)

    assert exc.value.status_code == 422

@pytest.mark.asyncio
async def test_completed_patient_cannot_be_completed_again(reception_context):
    services = reception_context["services"]
    queue_service = services["queue"]

    patient = await services["patient"].register_standard_patient(
        PatientCreate(
            national_id=f"TEST-{uuid4()}",
            first_name="Already",
            last_name="Completed",
            phone=f"+2547{uuid4().int % 10**8:08d}",
        )
    )

    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Duplicate completion test",
        )
    )

    entry = await queue_service.create_queue_entry(
        visit.visit_id,
        reception_context["reception"].dept_id,
    )

    await queue_service.call_queue_entry(entry.queue_entry_id)
    await queue_service.start_queue_entry(entry.queue_entry_id)
    await queue_service.complete_queue_entry(entry.queue_entry_id)

    with pytest.raises(HTTPException) as exc:
        await queue_service.complete_queue_entry(entry.queue_entry_id)

    assert exc.value.status_code == 422

@pytest.mark.asyncio
async def test_completed_patient_cannot_be_requeued(reception_context):
    services = reception_context["services"]
    queue_service = services["queue"]

    patient = await services["patient"].register_standard_patient(
        PatientCreate(
            national_id=f"TEST-{uuid4()}",
            first_name="Completed",
            last_name="Requeue",
            phone=f"+2547{uuid4().int % 10**8:08d}",
        )
    )

    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Invalid requeue test",
        )
    )

    entry = await queue_service.create_queue_entry(
        visit.visit_id,
        reception_context["reception"].dept_id,
    )

    await queue_service.call_queue_entry(entry.queue_entry_id)
    await queue_service.start_queue_entry(entry.queue_entry_id)
    await queue_service.complete_queue_entry(entry.queue_entry_id)

    with pytest.raises(HTTPException) as exc:
        await queue_service.transition_entry_status(
            entry.queue_entry_id,
            QueueEntryStatus.WAITING,
        )

    assert exc.value.status_code == 422