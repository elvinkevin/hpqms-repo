from fastapi import HTTPException, status
import pytest
from sqlalchemy import select

from app.domain.models.models import (
    EntryType,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    VisitStage,
)
from app.domain.schemas.schemas import (
    EmergencyPatientCreate,
    PatientCreate,
    VisitCreate,
)
from app.domain.services.patient_service import PatientService
from app.domain.services.visit_service import VisitService
from app.domain.services.queue_service import QueueService
from app.domain.services import routing_service

class TestQueueFIFO:
    """
    Validates FIFO behaviour for patients of the same priority.
    """

    @pytest.mark.asyncio
    async def test_fifo_queue_ordering(
        self,
        db,
        routing_departments,
    ):
        """
        Four walk-in patients arrive one after another.

        Expected:

        John
        ↓
        Mary
        ↓
        Peter
        ↓
        Jane

        Reception queue should preserve arrival order.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        arrivals = [
            ("John", "Doe", "10000001"),
            ("Mary", "Doe", "10000002"),
            ("Peter", "Doe", "10000003"),
            ("Jane", "Doe", "10000004"),
        ]

        queue_entries = []

        for index, (first, last, national_id) in enumerate(arrivals):

            patient = await patient_service.register_standard_patient(
                PatientCreate(
                    first_name=first,
                    last_name=last,
                    national_id=national_id,
                    phone=f"+2547000000{index}",
                    gender="MALE",
                    date_of_birth="1995-01-01",
                )
            )

            visit = await visit_service.start_visit(
                VisitCreate(
                    patient_id=patient.patient_id,
                    entry_type=EntryType.WALK_IN,
                    visit_reason="General Consultation",
                )
            )

            queue_entry = await queue_service.dispatch_initial_kiosk_route(
                visit.visit_id
            )

            queue_entries.append(queue_entry)

        # ------------------------------------------------------------------
        # Retrieve queue ordered by sequence
        # ------------------------------------------------------------------

        result = await db.execute(
            select(QueueEntry)
            .order_by(QueueEntry.sequence_number)
        )

        queue = result.scalars().all()

        # ------------------------------------------------------------------
        # Queue Assertions
        # ------------------------------------------------------------------

        assert len(queue) == 4

        for i, entry in enumerate(queue, start=1):

            assert entry.sequence_number == i
            assert entry.priority == QueuePriority.NORMAL
            assert entry.status == QueueEntryStatus.WAITING

        # ------------------------------------------------------------------
        # Verify arrival order preserved
        # ------------------------------------------------------------------

        assert queue[0].visit_id == queue_entries[0].visit_id
        assert queue[1].visit_id == queue_entries[1].visit_id
        assert queue[2].visit_id == queue_entries[2].visit_id
        assert queue[3].visit_id == queue_entries[3].visit_id

    @pytest.mark.asyncio
    async def test_queue_position_updates_after_call(
        self,
        db,
        routing_departments,
        receptionist,  # <-- Inject the valid staff fixture
    ):
        """
        Four walk-in patients arrive.

        John is called for consultation.

        Remaining waiting queue should preserve FIFO order.

        Waiting Queue:

        Mary
        Peter
        Jane
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        arrivals = [
            ("John", "Doe", "20000001"),
            ("Mary", "Doe", "20000002"),
            ("Peter", "Doe", "20000003"),
            ("Jane", "Doe", "20000004"),
        ]

        queue_entries = []

        # ---------------------------------------------------------
        # Register & route all patients
        # ---------------------------------------------------------

        for index, (first, last, national_id) in enumerate(arrivals):

            patient = await patient_service.register_standard_patient(
                PatientCreate(
                    first_name=first,
                    last_name=last,
                    national_id=national_id,
                    phone=f"+25471100000{index}",
                    gender="MALE",
                    date_of_birth="1995-01-01",
                )
            )

            visit = await visit_service.start_visit(
                VisitCreate(
                    patient_id=patient.patient_id,
                    entry_type=EntryType.WALK_IN,
                    visit_reason="General Consultation",
                )
            )

            queue_entry = await QueueService.dispatch_initial_kiosk_route(
                visit.visit_id
            )

            queue_entries.append(queue_entry)

        # ---------------------------------------------------------
        # Reception calls first patient
        # ---------------------------------------------------------

        called = await queue_service.call_queue_entry(
            queue_entry_id=queue_entries[0].queue_entry_id,
            staff_id=receptionist.staff_id  # <-- Pass the mandatory staff_id
        )

        assert called.status == QueueEntryStatus.CALLED

        # ---------------------------------------------------------
        # Remaining WAITING queue
        # ---------------------------------------------------------

        result = await db.execute(
            select(QueueEntry)
            .where(
                QueueEntry.status == QueueEntryStatus.WAITING
            )
            .order_by(QueueEntry.sequence_number)
        )

        waiting_queue = result.scalars().all()

        assert len(waiting_queue) == 3

        # FIFO should remain intact
        assert waiting_queue[0].visit_id == queue_entries[1].visit_id
        assert waiting_queue[1].visit_id == queue_entries[2].visit_id
        assert waiting_queue[2].visit_id == queue_entries[3].visit_id

        # ---------------------------------------------------------
        # Status validation
        # ---------------------------------------------------------

        await db.refresh(queue_entries[1])
        await db.refresh(queue_entries[2])
        await db.refresh(queue_entries[3])

        assert queue_entries[1].status == QueueEntryStatus.WAITING
        assert queue_entries[2].status == QueueEntryStatus.WAITING
        assert queue_entries[3].status == QueueEntryStatus.WAITING

        # ---------------------------------------------------------
        # Exactly one patient is CALLED
        # ---------------------------------------------------------

        result = await db.execute(
            select(QueueEntry).where(
                QueueEntry.status == QueueEntryStatus.CALLED
            )
        )

        called_entries = result.scalars().all()

        assert len(called_entries) == 1
        assert called_entries[0].queue_entry_id == queue_entries[0].queue_entry_id


    

class TestEmergencyPriority:

    @pytest.mark.asyncio
    async def test_emergency_patient_preempts_existing_queue(
        self,
        db,
        routing_departments,
    ):
        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        visits = []

        # ----------------------------------------
        # Two normal walk-ins
        # ----------------------------------------
        for i in range(2):
            patient = await patient_service.register_standard_patient(
                PatientCreate(
                    first_name=f"Walk{i}",
                    last_name="Patient",
                    national_id=f"90000{i}",
                    phone=f"+2547000000{i}",
                    gender="MALE",
                    date_of_birth="1995-01-01",
                )
            )

            visit = await visit_service.start_visit(
                VisitCreate(
                    patient_id=patient.patient_id,
                    entry_type=EntryType.WALK_IN,
                    visit_reason="General Consultation",
                )
            )

            await routing_service.dispatch_initial_kiosk_route(
                visit.visit_id
            )

            visits.append(visit)

        # ----------------------------------------
        # Emergency patient arrives later
        # ----------------------------------------
        emergency_patient = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="John",
                last_name="Doe",
                estimated_age=35,
                gender="MALE",
            )
        )

        emergency_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=emergency_patient.patient_id,
                entry_type=EntryType.EMERGENCY,
                visit_reason="Road Traffic Accident",
            )
        )

        emergency_queue = await routing_service.dispatch_initial_kiosk_route(
            emergency_visit.visit_id
        )

        # ----------------------------------------
        # Assertions
        # ----------------------------------------

        assert emergency_queue.priority == QueuePriority.CRITICAL

        assert (
            emergency_queue.department_id
            == routing_departments["emergency"].dept_id
        )

        assert emergency_queue.status == QueueEntryStatus.WAITING





class TestPatientRevisit:

    @pytest.mark.asyncio
    async def test_patient_can_start_new_visit_after_completion(
        self,
        db,
    ):
        """
        A patient may begin another visit once
        the previous visit has been completed.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)

        # -----------------------------------------
        # Register patient
        # -----------------------------------------

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Repeat",
                last_name="Visitor",
                national_id="44556677",
                phone="+254711223355",
                gender="MALE",
                date_of_birth="1990-01-01",
            )
        )

        # -----------------------------------------
        # First visit
        # -----------------------------------------

        visit_one = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Headache",
            )
        )

        assert visit_one.stage == VisitStage.ACTIVE

        # Complete first visit

        completed = await visit_service.complete_visit(
            visit_one.visit_id
        )

        assert completed.stage == VisitStage.COMPLETED

        # -----------------------------------------
        # Second visit
        # -----------------------------------------

        visit_two = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Follow-up Review",
            )
        )

        # -----------------------------------------
        # Assertions
        # -----------------------------------------

        assert visit_two.visit_id != visit_one.visit_id

        assert visit_two.patient_id == patient.patient_id

        assert visit_two.stage == VisitStage.ACTIVE

        # New token generated

        assert visit_two.token_number != visit_one.token_number

class TestQueueCompletionConsistency:

    @pytest.mark.asyncio
    async def test_visit_not_completed_until_final_department(
        self,
        db,
        routing_departments,
    ):
        """
        Completing an intermediate department must not
        automatically complete the visit.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        QueueService = QueueService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="John",
                last_name="Walker",
                national_id="55555555",
                phone="+254700111555",
                gender="MALE",
                date_of_birth="1995-05-20",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="General Consultation",
            )
        )

        reception = await QueueService.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        await QueueService.call_queue_entry(reception.queue_entry_id)
        await QueueService.start_queue_entry(reception.queue_entry_id)
        await QueueService.complete_queue_entry(reception.queue_entry_id)

        await db.refresh(visit)

        assert visit.stage == VisitStage.ACTIVE

class TestCompletedQueueProtection:

     @pytest.mark.asyncio
     async def test_completed_queue_entry_cannot_transfer(
        self,
        db,
        routing_departments,
        receptionist,  # <-- Inject the valid staff fixture
    ):
        """
        Completed queue entries cannot be reused
        for additional department transfers.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        QueueService = QueueService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Mary",
                last_name="Jones",
                national_id="66666666",
                phone="+254700222333",
                gender="FEMALE",
                date_of_birth="1992-06-12",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Follow-up",
            )
        )

        queue = await QueueService.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        # Pass staff_id into every mutation call
        await QueueService.call_queue_entry(queue_entry_id=queue.queue_entry_id, staff_id=receptionist.staff_id)
        await QueueService.start_queue_entry(queue_entry_id=queue.queue_entry_id, staff_id=receptionist.staff_id)
        await QueueService.complete_queue_entry(queue_entry_id=queue.queue_entry_id, staff_id=receptionist.staff_id)

        with pytest.raises(HTTPException):
            await QueueService.start_queue_entry(
                queue_entry_id=queue.queue_entry_id,
                staff_id=receptionist.staff_id  # <-- Pass the staff_id here too
            )

class TestCompletedQueueState:

    @pytest.mark.asyncio
    async def test_completed_queue_cannot_be_called_again(
        self,
        db,
        routing_departments,
    ):
        """
        Once completed, queue state is terminal.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        QueueService = QueueService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Alice",
                last_name="Brown",
                national_id="77777777",
                phone="+254700555111",
                gender="FEMALE",
                date_of_birth="1994-02-11",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Consultation",
            )
        )

        queue = await QueueService.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        await QueueService.call_queue_entry(queue.queue_entry_id)
        await QueueService.start_queue_entry(queue.queue_entry_id)
        await QueueService.complete_queue_entry(queue.queue_entry_id)

        with pytest.raises(HTTPException):
            await QueueService.call_queue_entry(queue.queue_entry_id)

class TestQueueHistory:

    @pytest.mark.asyncio
    async def test_queue_history_is_preserved(
        self,
        db,
        routing_departments,
    ):
        """
        Every department transfer creates a historical queue entry
        while preserving the patient's journey.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        QueueService = QueueService(db)

        # --------------------------------------------------
        # Register patient
        # --------------------------------------------------

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Kevin",
                last_name="History",
                national_id="88888888",
                phone="+254700888888",
                gender="MALE",
                date_of_birth="1990-01-01",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Routine Consultation",
            )
        )

        # --------------------------------------------------
        # Reception
        # --------------------------------------------------

        reception = await QueueService.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        await QueueService.call_queue_entry(
            reception.queue_entry_id
        )

        await QueueService.start_queue_entry(
            reception.queue_entry_id
        )

        await QueueService.complete_queue_entry(
            reception.queue_entry_id
        )

        # --------------------------------------------------
        # Move to Triage
        # --------------------------------------------------

        triage = await QueueService.move_patient(
            visit_id=visit.visit_id,
            target_department_id=routing_departments["triage"].dept_id,
            priority=QueuePriority.NORMAL,
            notes="Transferred to triage",
        )

        # --------------------------------------------------
        # Query queue history directly
        # --------------------------------------------------

        result = await db.execute(
            select(QueueEntry)
            .where(QueueEntry.visit_id == visit.visit_id)
            .order_by(QueueEntry.entered_at)
        )

        history = result.scalars().all()

        assert len(history) == 2

        reception_history = next(
            e
            for e in history
            if e.department_id
            == routing_departments["reception"].dept_id
        )

        triage_history = next(
            e
            for e in history
            if e.department_id
            == routing_departments["triage"].dept_id
        )

        # --------------------------------------------------
        # Historical integrity
        # --------------------------------------------------

        assert reception_history.status == QueueEntryStatus.COMPLETED
        assert triage_history.status == QueueEntryStatus.WAITING

        assert reception_history.queue_entry_id != triage_history.queue_entry_id

        # --------------------------------------------------
        # Visit pointer
        # --------------------------------------------------

        await db.refresh(visit)

        assert visit.current_queue_entry_id == triage.queue_entry_id



class TestVisitCompletionRules:

    @pytest.mark.asyncio
    async def test_visit_cannot_complete_with_active_queue_entry(
        self,
        db,
        routing_departments,
    ):
        """
        Visits cannot finish while the patient
        is still waiting somewhere.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        QueueService = QueueService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="David",
                last_name="Queue",
                national_id="99999991",
                phone="+254711111111",
                gender="MALE",
                date_of_birth="1995-03-20",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Consultation",
            )
        )

        await QueueService.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        with pytest.raises(HTTPException):
            await visit_service.complete_visit(
                visit.visit_id
            )