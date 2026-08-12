import pytest
from fastapi import HTTPException, status
from sqlalchemy import select

from app.domain.models.models import (
    DepartmentQueueCounter,
    EntryType,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
)
from app.domain.services.queue_service import AVG_CONSULT_MINUTES, QueueService
from uuid import uuid4

from app.domain.schemas.schemas import PatientCreate, VisitCreate
from app.domain.services import patient_service
from app.domain.services.visit_service import VisitService
from tests.conftest import existing_patient
from app.domain.services.patient_service import PatientService
class TestQueueCreation:

    @pytest.mark.asyncio
    async def test_create_queue_entry_success(
        self,
        db,
        active_visit,
        routing_departments,
    ):
        service = QueueService(db)

        entry = await service.create_queue_entry(
            visit_id=active_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
            notes="Initial queue entry",
        )

        assert entry.queue_entry_id is not None
        assert entry.visit_id == active_visit.visit_id
        assert (
            entry.department_id
            == routing_departments["reception"].dept_id
        )
        assert entry.priority == QueuePriority.NORMAL
        assert entry.status == QueueEntryStatus.WAITING
        assert entry.sequence_number is not None
        assert entry.notes == "Initial queue entry"


    @pytest.mark.asyncio
    async def test_create_queue_entry_rejects_invalid_visit(
        self,
        db,
        routing_departments,
    ):
        service = QueueService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_queue_entry(
                visit_id=uuid4(),
                department_id=routing_departments["reception"].dept_id,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Visit" in exc_info.value.detail


    @pytest.mark.asyncio
    async def test_create_queue_entry_rejects_invalid_department(
        self,
        db,
        active_visit,
    ):
        service = QueueService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_queue_entry(
                visit_id=active_visit.visit_id,
                department_id=uuid4(),
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Department" in exc_info.value.detail


    @pytest.mark.asyncio
    async def test_visit_cannot_have_two_active_queue_entries(
        self,
        db,
        active_visit,
        routing_departments,
    ):
        service = QueueService(db)

        first = await service.create_queue_entry(
            visit_id=active_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
        )

        assert first.status == QueueEntryStatus.WAITING

        with pytest.raises(HTTPException) as exc_info:
            await service.create_queue_entry(
                visit_id=active_visit.visit_id,
                department_id=routing_departments["triage"].dept_id,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already has an active queue entry" in exc_info.value.detail


    @pytest.mark.asyncio
    async def test_queue_sequence_increments_within_department(
        self,
        db,
        existing_patient,  # <--- Added missing fixture argument
        routing_departments,
    ):
        service = QueueService(db)
        visit_service = VisitService(db)
        patient_service = PatientService(db)

        visit_one = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="First visit",
            )
        )

        # Need another patient because one patient cannot have
        # two active visits.
        second_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Second",
                last_name="Patient",
                national_id="90000001",
                phone="+254700000001",
                gender="MALE",
            )
        )

        visit_two = await visit_service.start_visit(
            VisitCreate(
                patient_id=second_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Second visit",
            )
        )

        first_entry = await service.create_queue_entry(
            visit_id=visit_one.visit_id,
            department_id=routing_departments["reception"].dept_id,
        )

        second_entry = await service.create_queue_entry(
            visit_id=visit_two.visit_id,
            department_id=routing_departments["reception"].dept_id,
        )

        assert second_entry.sequence_number == first_entry.sequence_number + 1




class TestQueueOrdering:

    @pytest.mark.asyncio
    async def test_get_department_queue_returns_fifo_order(
        self,
        db,
        existing_patient,
        routing_departments,
    ):
        """
        Patients with the same priority are ordered by sequence number.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        # --------------------------------------------------
        # Create second patient
        # --------------------------------------------------

        second_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Second",
                last_name="FIFO",
                national_id="70000001",
                phone="+254700000001",
                gender="MALE",
                date_of_birth="1995-01-01",
            )
        )

        # --------------------------------------------------
        # Create visits
        # --------------------------------------------------

        first_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="First patient",
            )
        )

        second_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=second_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Second patient",
            )
        )

        # --------------------------------------------------
        # Create queue entries
        # --------------------------------------------------

        first_entry = await queue_service.create_queue_entry(
            visit_id=first_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        second_entry = await queue_service.create_queue_entry(
            visit_id=second_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        # --------------------------------------------------
        # Retrieve queue
        # --------------------------------------------------

        queue = await queue_service.get_department_queue(
            routing_departments["reception"].dept_id
        )

        assert len(queue) == 2

        assert queue[0].queue_entry_id == first_entry.queue_entry_id
        assert queue[1].queue_entry_id == second_entry.queue_entry_id

        assert queue[0].sequence_number < queue[1].sequence_number

    @pytest.mark.asyncio
    async def test_critical_patient_preempts_normal_patient(
        self,
        db,
        existing_patient,
        routing_departments,
    ):
        """
        Priority takes precedence over arrival sequence.

        NORMAL arrives first
        CRITICAL arrives second

        Expected:
        CRITICAL
        NORMAL
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        # --------------------------------------------------
        # Second patient
        # --------------------------------------------------

        emergency_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Critical",
                last_name="Patient",
                national_id="70000002",
                phone="+254700000002",
                gender="MALE",
                date_of_birth="1990-01-01",
            )
        )

        # --------------------------------------------------
        # Visits
        # --------------------------------------------------

        normal_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Normal case",
            )
        )

        critical_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=emergency_patient.patient_id,
                entry_type=EntryType.EMERGENCY,
                visit_reason="Critical case",
            )
        )

        # --------------------------------------------------
        # Queue entries
        # --------------------------------------------------

        normal_entry = await queue_service.create_queue_entry(
            visit_id=normal_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        critical_entry = await queue_service.create_queue_entry(
            visit_id=critical_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.CRITICAL,
        )

        # --------------------------------------------------
        # Retrieve queue
        # --------------------------------------------------

        queue = await queue_service.get_department_queue(
            routing_departments["reception"].dept_id
        )

        assert len(queue) == 2

        assert queue[0].queue_entry_id == critical_entry.queue_entry_id
        assert queue[1].queue_entry_id == normal_entry.queue_entry_id

        assert queue[0].priority == QueuePriority.CRITICAL
        assert queue[1].priority == QueuePriority.NORMAL

    @pytest.mark.asyncio
    async def test_get_next_patient_returns_highest_priority_waiting_patient(
        self,
        db,
        existing_patient,
        routing_departments,
    ):
        """
        get_next_patient() returns the highest-priority WAITING
        patient according to priority + FIFO ordering.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        queue_service = QueueService(db)

        second_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Next",
                last_name="Patient",
                national_id="70000004",
                phone="+254700000004",
                gender="MALE",
                date_of_birth="1991-01-01",
            )
        )

        normal_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Normal",
            )
        )

        urgent_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=second_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Urgent",
            )
        )

        normal_entry = await queue_service.create_queue_entry(
            visit_id=normal_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        urgent_entry = await queue_service.create_queue_entry(
            visit_id=urgent_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.URGENT,
        )

        next_patient = await queue_service.get_next_patient(
            routing_departments["reception"].dept_id
        )

        assert next_patient is not None
        assert next_patient.queue_entry_id == urgent_entry.queue_entry_id
        assert next_patient.priority == QueuePriority.URGENT

        assert next_patient.queue_entry_id != normal_entry.queue_entry_id

# ============================================================
# BATCH 2 — QUEUE STATE TRANSITIONS
# ============================================================

class TestQueueStateTransitions:

    @pytest.mark.asyncio
    async def test_waiting_to_called(
        self,
        db,
        queue_entry,
    ):
        """
        WAITING -> CALLED

        A waiting patient can be called by queue staff.
        """

        service = QueueService(db)

        assert queue_entry.status == QueueEntryStatus.WAITING

        updated = await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        assert updated.status == QueueEntryStatus.CALLED


    @pytest.mark.asyncio
    async def test_called_to_in_progress(
        self,
        db,
        queue_entry,
    ):
        """
        WAITING -> CALLED -> IN_PROGRESS

        Once the patient has been called,
        staff can begin processing the patient.
        """

        service = QueueService(db)

        await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        updated = await service.start_queue_entry(
            queue_entry.queue_entry_id
        )

        assert updated.status == QueueEntryStatus.IN_PROGRESS


    @pytest.mark.asyncio
    async def test_in_progress_to_completed(
        self,
        db,
        queue_entry,
    ):
        """
        WAITING -> CALLED -> IN_PROGRESS -> COMPLETED

        A patient currently being served can have
        their queue entry completed.
        """

        service = QueueService(db)

        await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        await service.start_queue_entry(
            queue_entry.queue_entry_id
        )

        updated = await service.complete_queue_entry(
            queue_entry.queue_entry_id
        )

        assert updated.status == QueueEntryStatus.COMPLETED


    @pytest.mark.asyncio
    async def test_called_to_no_show(
        self,
        db,
        queue_entry,
    ):
        """
        WAITING -> CALLED -> NO_SHOW

        A patient who was called but failed to appear
        can be marked as a no-show.
        """

        service = QueueService(db)

        await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        updated = await service.mark_no_show(
            queue_entry.queue_entry_id,
            notes="Patient did not respond when called.",
        )

        assert updated.status == QueueEntryStatus.NO_SHOW


    @pytest.mark.asyncio
    async def test_active_queue_entry_can_be_cancelled(
        self,
        db,
        queue_entry,
    ):
        """
        An active queue entry can be cancelled.
        """

        service = QueueService(db)

        updated = await service.cancel_queue_entry(
            queue_entry.queue_entry_id,
            notes="Patient requested cancellation.",
        )

        assert updated.status == QueueEntryStatus.CANCELLED


    @pytest.mark.asyncio
    async def test_invalid_waiting_to_in_progress_transition_rejected(
        self,
        db,
        queue_entry,
    ):
        """
        WAITING -> IN_PROGRESS is invalid.

        A patient must first be CALLED.
        """

        service = QueueService(db)

        assert queue_entry.status == QueueEntryStatus.WAITING

        with pytest.raises(HTTPException) as exc_info:
            await service.start_queue_entry(
                queue_entry.queue_entry_id
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


    @pytest.mark.asyncio
    async def test_invalid_waiting_to_completed_transition_rejected(
        self,
        db,
        queue_entry,
    ):
        """
        WAITING -> COMPLETED is invalid.

        A patient must be called and started first.
        """

        service = QueueService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.complete_queue_entry(
                queue_entry.queue_entry_id
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


    @pytest.mark.asyncio
    async def test_completed_queue_entry_cannot_be_called_again(
        self,
        db,
        queue_entry,
    ):
        """
        COMPLETED is terminal.

        A completed queue entry cannot return to CALLED.
        """

        service = QueueService(db)

        await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        await service.start_queue_entry(
            queue_entry.queue_entry_id
        )

        await service.complete_queue_entry(
            queue_entry.queue_entry_id
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.call_queue_entry(
                queue_entry.queue_entry_id
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


    @pytest.mark.asyncio
    async def test_no_show_queue_entry_cannot_be_started(
        self,
        db,
        queue_entry,
    ):
        """
        NO_SHOW is terminal.

        A no-show patient cannot subsequently enter treatment
        through the same queue entry.
        """

        service = QueueService(db)

        await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        await service.mark_no_show(
            queue_entry.queue_entry_id
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.start_queue_entry(
                queue_entry.queue_entry_id
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


    @pytest.mark.asyncio
    async def test_cancelled_queue_entry_cannot_be_called(
        self,
        db,
        queue_entry,
    ):
        """
        CANCELLED is terminal.

        A cancelled queue entry cannot be called again.
        """

        service = QueueService(db)

        await service.cancel_queue_entry(
            queue_entry.queue_entry_id,
            notes="Cancelled before service.",
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.call_queue_entry(
                queue_entry.queue_entry_id
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

# ============================================================
# BATCH 3 — QUEUE ANALYTICS & LINE METRICS
# ============================================================

class TestQueueAnalytics:

    @pytest.mark.asyncio
    async def test_first_patient_position_is_one(
        self,
        db,
        queue_entry,
    ):
        """
        The first active patient in a department queue
        should have position 1.
        """

        service = QueueService(db)

        position = await service.get_patient_position(
            queue_entry.queue_entry_id
        )

        assert position == 1


    @pytest.mark.asyncio
    async def test_fifo_patient_position(
        self,
        db,
        routing_departments,
        existing_patient,
    ):
        """
        Patients with the same priority are ordered FIFO.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        service = QueueService(db)

        # First patient
        first_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="First patient",
            )
        )

        first_entry = await service.create_queue_entry(
            visit_id=first_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        # Second patient
        second_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Second",
                last_name="Patient",
                national_id="70000002",
                phone="+254700000002",
                gender="MALE",
                date_of_birth="1995-01-01",
            )
        )

        second_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=second_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Second patient",
            )
        )

        second_entry = await service.create_queue_entry(
            visit_id=second_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        first_position = await service.get_patient_position(
            first_entry.queue_entry_id
        )

        second_position = await service.get_patient_position(
            second_entry.queue_entry_id
        )

        assert first_position == 1
        assert second_position == 2


    @pytest.mark.asyncio
    async def test_critical_patient_gets_priority_position(
        self,
        db,
        routing_departments,
        existing_patient,
    ):
        """
        A CRITICAL patient should move ahead of an existing
        NORMAL patient regardless of sequence number.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        service = QueueService(db)

        normal_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Normal patient",
            )
        )

        normal_entry = await service.create_queue_entry(
            visit_id=normal_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        critical_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Critical",
                last_name="Patient",
                national_id="70000003",
                phone="+254700000003",
                gender="MALE",
                date_of_birth="1995-01-01",
            )
        )

        critical_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=critical_patient.patient_id,
                entry_type=EntryType.EMERGENCY,
                visit_reason="Critical emergency",
            )
        )

        critical_entry = await service.create_queue_entry(
            visit_id=critical_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.CRITICAL,
        )

        critical_position = await service.get_patient_position(
            critical_entry.queue_entry_id
        )

        normal_position = await service.get_patient_position(
            normal_entry.queue_entry_id
        )

        assert critical_position == 1
        assert normal_position == 2


    @pytest.mark.asyncio
    async def test_position_updates_after_patient_ahead_completes(
        self,
        db,
        routing_departments,
        existing_patient,
    ):
        """
        When the patient ahead completes their queue entry,
        the next patient's position should decrease.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        service = QueueService(db)

        first_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="First",
            )
        )

        first_entry = await service.create_queue_entry(
            visit_id=first_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        second_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Next",
                last_name="Patient",
                national_id="70000004",
                phone="+254700000004",
                gender="MALE",
                date_of_birth="1995-01-01",
            )
        )

        second_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=second_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Second",
            )
        )

        second_entry = await service.create_queue_entry(
            visit_id=second_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        assert await service.get_patient_position(
            second_entry.queue_entry_id
        ) == 2

        await service.call_queue_entry(first_entry.queue_entry_id)
        await service.start_queue_entry(first_entry.queue_entry_id)
        await service.complete_queue_entry(first_entry.queue_entry_id)

        assert await service.get_patient_position(
            second_entry.queue_entry_id
        ) == 1

# ============================================================
# BATCH 3 — FINAL QUEUE ANALYTICS TESTS
# ============================================================

class TestQueueAnalyticsFinal:

    @pytest.mark.asyncio
    async def test_first_patient_has_zero_estimated_wait_time(
        self,
        db,
        queue_entry,
    ):
        """
        The first patient in an active queue has nobody ahead,
        therefore their estimated wait time is zero.
        """

        service = QueueService(db)

        position = await service.get_patient_position(
            queue_entry.queue_entry_id
        )

        wait_time = await service.get_estimated_wait_time(
            queue_entry.queue_entry_id
        )

        assert position == 1
        assert wait_time == 0


    @pytest.mark.asyncio
    async def test_second_patient_wait_time_equals_one_consultation(
        self,
        db,
        routing_departments,
        existing_patient,
    ):
        """
        With one patient ahead, estimated wait time should equal
        one average consultation duration.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        service = QueueService(db)

        first_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="First patient",
            )
        )

        first_entry = await service.create_queue_entry(
            visit_id=first_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        second_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Second",
                last_name="Wait",
                national_id="71000001",
                phone="+254710000001",
                gender="MALE",
                date_of_birth="1995-01-01",
            )
        )

        second_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=second_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Second patient",
            )
        )

        second_entry = await service.create_queue_entry(
            visit_id=second_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        wait_time = await service.get_estimated_wait_time(
            second_entry.queue_entry_id
        )

        assert await service.get_patient_position(
            first_entry.queue_entry_id
        ) == 1

        assert await service.get_patient_position(
            second_entry.queue_entry_id
        ) == 2

        assert wait_time == AVG_CONSULT_MINUTES


    @pytest.mark.asyncio
    async def test_completed_entry_returns_zero_position(
        self,
        db,
        queue_entry,
    ):
        """
        Completed queue entries are no longer active and therefore
        have no queue position.
        """

        service = QueueService(db)

        await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        await service.start_queue_entry(
            queue_entry.queue_entry_id
        )

        await service.complete_queue_entry(
            queue_entry.queue_entry_id
        )

        position = await service.get_patient_position(
            queue_entry.queue_entry_id
        )

        wait_time = await service.get_estimated_wait_time(
            queue_entry.queue_entry_id
        )

        assert position == 0
        assert wait_time == 0


    @pytest.mark.asyncio
    async def test_no_show_entry_returns_zero_position(
        self,
        db,
        queue_entry,
    ):
        """
        A NO_SHOW queue entry is no longer active.
        """

        service = QueueService(db)

        await service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        await service.mark_no_show(
            queue_entry.queue_entry_id
        )

        position = await service.get_patient_position(
            queue_entry.queue_entry_id
        )

        wait_time = await service.get_estimated_wait_time(
            queue_entry.queue_entry_id
        )

        assert position == 0
        assert wait_time == 0


    @pytest.mark.asyncio
    async def test_cancelled_entry_returns_zero_position(
        self,
        db,
        queue_entry,
    ):
        """
        A CANCELLED queue entry is no longer active.
        """

        service = QueueService(db)

        await service.cancel_queue_entry(
            queue_entry.queue_entry_id,
            notes="Patient cancelled queue entry.",
        )

        position = await service.get_patient_position(
            queue_entry.queue_entry_id
        )

        wait_time = await service.get_estimated_wait_time(
            queue_entry.queue_entry_id
        )

        assert position == 0
        assert wait_time == 0


    @pytest.mark.asyncio
    async def test_queue_position_is_isolated_by_department(
        self,
        db,
        routing_departments,
        existing_patient,
    ):
        """
        Queue position is calculated independently per department.

        A patient waiting in Reception must not affect the position
        of a patient waiting in Triage.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        service = QueueService(db)

        # --------------------------------------------------
        # Reception patient
        # --------------------------------------------------

        reception_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=existing_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Reception",
            )
        )

        reception_entry = await service.create_queue_entry(
            visit_id=reception_visit.visit_id,
            department_id=routing_departments["reception"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        # --------------------------------------------------
        # Triage patient
        # --------------------------------------------------

        triage_patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Triage",
                last_name="Patient",
                national_id="71000002",
                phone="+254710000002",
                gender="FEMALE",
                date_of_birth="1995-01-01",
            )
        )

        triage_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=triage_patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Triage",
            )
        )

        triage_entry = await service.create_queue_entry(
            visit_id=triage_visit.visit_id,
            department_id=routing_departments["triage"].dept_id,
            priority=QueuePriority.NORMAL,
        )

        # Each department has its own queue.
        assert await service.get_patient_position(
            reception_entry.queue_entry_id
        ) == 1

        assert await service.get_patient_position(
            triage_entry.queue_entry_id
        ) == 1

