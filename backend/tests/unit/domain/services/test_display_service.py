import uuid

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from app.domain.models.models import (
    Department,
    DeptType,
    EntryType,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    RegistrationStatus,
    Visit,
    VisitStage,
)
from app.domain.services.display_service import DisplayService
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock


@pytest.fixture
def patient_factory(db):
    """
    Factory fixture to dynamically create multiple unique patient records.
    Generates random unique strings to satisfy unique constraints on
    temporary_identifier, national_id, and phone.
    """
    async def _create_patient():
        # Generate a short random string to guarantee uniqueness
        unique_suffix = uuid.uuid4().hex[:8]
        
        new_patient = Patient(
            patient_id=uuid.uuid4(),
            registration_status=RegistrationStatus.INCOMPLETE,
            
            # Satisfy unique database constraints
            temporary_identifier=f"TEMP-{unique_suffix}",
            national_id=f"NAT-{unique_suffix}",
            phone=f"+254700{uuid.uuid4().int % 1000000:06d}", # Generates random number string
            
            # Basic demographics
            first_name="Integration",
            last_name=f"Patient-{unique_suffix}",
            gender="UNKNOWN",
            is_active=True
        )
        db.add(new_patient)
        await db.flush()
        return new_patient
        
    return _create_patient
class TestDisplaySnapshot:

    @pytest.mark.asyncio
    async def test_empty_hospital_returns_empty_snapshot(
        self,
        db,
    ):
        service = DisplayService(
            db,
            facility_name="HPQMS Hospital",
        )

        snapshot = await service.get_snapshot()

        assert snapshot.facility_name == "HPQMS Hospital"
        assert snapshot.departments == []
        assert snapshot.announcements == []
        assert snapshot.server_timestamp is not None

    @pytest.mark.asyncio
    async def test_snapshot_includes_active_departments_only(
        self,
        db,
    ):
        active_department = Department(
            name="Reception",
            department_code="REC",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        inactive_department = Department(
            name="Laboratory",
            department_code="LAB",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=False,
        )

        db.add_all([
            active_department,
            inactive_department,
        ])

        await db.flush()

        service = DisplayService(db)

        snapshot = await service.get_snapshot()

        assert len(snapshot.departments) == 1
        assert snapshot.departments[0].department_name == "Reception"

    @pytest.mark.asyncio
    async def test_snapshot_departments_are_ordered_by_name(
        self,
        db,
    ):
        pharmacy = Department(
            name="Pharmacy",
            department_code="PHARM",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        reception = Department(
            name="Reception",
            department_code="REC",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        laboratory = Department(
            name="Laboratory",
            department_code="LAB",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add_all([
            pharmacy,
            reception,
            laboratory,
        ])

        await db.flush()

        service = DisplayService(db)

        snapshot = await service.get_snapshot()

        names = [
            department.department_name
            for department in snapshot.departments
        ]

        assert names == [
            "Laboratory",
            "Pharmacy",
            "Reception",
        ]

class TestDepartmentQueueState:

    @pytest.mark.asyncio
    async def test_empty_department_has_empty_queue_state(
        self,
        db,
    ):
        department = Department(
            name="Pharmacy",
            department_code="PHARM",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        assert display.dept_id == department.dept_id
        assert display.department_name == "Pharmacy"

        assert display.active_tokens == []
        assert display.next_tokens == []
        assert display.recent_tokens == []

        assert display.waiting_count == 0
        assert display.estimated_wait_minutes == 0

    @pytest.mark.asyncio
    async def test_active_tokens_include_called_and_in_progress(
        self,
        db,
        existing_patient,
    ):
        department = Department(
            name="Reception",
            department_code="REC",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        visit_called = Visit(
            patient_id=existing_patient.patient_id,
            token_number="A-001",
            entry_type=EntryType.WALK_IN,
            stage=VisitStage.ACTIVE,
        )

        visit_in_progress = Visit(
            patient_id=existing_patient.patient_id,
            token_number="A-002",
            entry_type=EntryType.WALK_IN,
            stage=VisitStage.ACTIVE,
        )

        db.add_all([
            visit_called,
            visit_in_progress,
        ])

        await db.flush()

        called_entry = QueueEntry(
            visit_id=visit_called.visit_id,
            dept_id=department.dept_id,
            sequence_number=1,
            priority=QueuePriority.NORMAL,
            status=QueueEntryStatus.CALLED,
        )

        in_progress_entry = QueueEntry(
            visit_id=visit_in_progress.visit_id,
            dept_id=department.dept_id,
            sequence_number=2,
            priority=QueuePriority.NORMAL,
            status=QueueEntryStatus.IN_PROGRESS,
        )

        db.add_all([
            called_entry,
            in_progress_entry,
        ])

        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        tokens = {
            token.token_number: token.status
            for token in display.active_tokens
        }

        assert tokens["A-001"] == QueueEntryStatus.CALLED
        assert tokens["A-002"] == QueueEntryStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_waiting_tokens_appear_as_next_tokens(
        self,
        db,                # Changed from db
        existing_patient,  # Changed from patient
    ):
        department = Department(
            name="Laboratory",
            department_code="LAB",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        visit = Visit(
            patient_id=existing_patient.patient_id,  # Changed from patient
            token_number="L-001",
            entry_type=EntryType.WALK_IN,
            stage=VisitStage.ACTIVE,
        )

        db.add(visit)
        await db.flush()

        queue_entry = QueueEntry(
            visit_id=visit.visit_id,
            dept_id=department.dept_id,
            sequence_number=1,
            priority=QueuePriority.NORMAL,
            status=QueueEntryStatus.WAITING,
        )

        db.add(queue_entry)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        assert len(display.next_tokens) == 1
        assert display.next_tokens[0].token_number == "L-001"


    @pytest.mark.asyncio
    async def test_completed_tokens_appear_as_recent_tokens(
        self,
        db,                # Changed from db
        existing_patient,  # Changed from patient
    ):
        department = Department(
            name="Pharmacy",
            department_code="PHARM",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        visit = Visit(
            patient_id=existing_patient.patient_id,  # Changed from patient
            token_number="P-001",
            entry_type=EntryType.WALK_IN,
            stage=VisitStage.COMPLETED,
        )

        db.add(visit)
        await db.flush()

        completed_at = datetime.now(timezone.utc)

        queue_entry = QueueEntry(
            visit_id=visit.visit_id,
            dept_id=department.dept_id,
            sequence_number=1,
            priority=QueuePriority.NORMAL,
            status=QueueEntryStatus.COMPLETED,
            completed_at=completed_at,
        )

        db.add(queue_entry)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        assert len(display.recent_tokens) == 1
        assert display.recent_tokens[0].token_number == "P-001"

        assert display.active_tokens == []
        assert display.next_tokens == []

    @pytest.mark.asyncio
    async def test_next_tokens_follow_priority_then_sequence(
        self,
        db,  # Changed from db
        patient_factory,
    ):
        department = Department(
            name="Triage",
            department_code="TRI",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        patients = [
            await patient_factory(),
            await patient_factory(),
            await patient_factory(),
            await patient_factory(),
        ]

        visits = [
            Visit(
                patient_id=patients[0].patient_id,
                token_number="T-001",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.ACTIVE,
            ),
            Visit(
                patient_id=patients[1].patient_id,
                token_number="T-002",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.ACTIVE,
            ),
            Visit(
                patient_id=patients[2].patient_id,
                token_number="T-003",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.ACTIVE,
            ),
            Visit(
                patient_id=patients[3].patient_id,
                token_number="T-004",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.ACTIVE,
            ),
        ]

        db.add_all(visits)
        await db.flush()

        entries = [
            QueueEntry(
                visit_id=visits[0].visit_id,
                dept_id=department.dept_id,
                sequence_number=1,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.WAITING,
            ),
            QueueEntry(
                visit_id=visits[1].visit_id,
                dept_id=department.dept_id,
                sequence_number=2,
                priority=QueuePriority.URGENT,
                status=QueueEntryStatus.WAITING,
            ),
            QueueEntry(
                visit_id=visits[2].visit_id,
                dept_id=department.dept_id,
                sequence_number=3,
                priority=QueuePriority.CRITICAL,
                status=QueueEntryStatus.WAITING,
            ),
            QueueEntry(
                visit_id=visits[3].visit_id,
                dept_id=department.dept_id,
                sequence_number=4,
                priority=QueuePriority.URGENT,
                status=QueueEntryStatus.WAITING,
            ),
        ]

        db.add_all(entries)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        tokens = [
            token.token_number
            for token in display.next_tokens
        ]

        assert tokens == [
            "T-003",  # CRITICAL
            "T-002",  # URGENT, sequence 2
            "T-004",  # URGENT, sequence 4
            "T-001",  # NORMAL (default next_limit is 4)
        ]

    @pytest.mark.asyncio
    async def test_next_tokens_respect_limit(
        self,
        db,
        patient_factory,
    ):
        department = Department(
            name="Pharmacy",
            department_code="PHARM",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        patients = [
            await patient_factory()
            for _ in range(4)
        ]

        visits = []

        for index, patient in enumerate(patients, start=1):
            visit = Visit(
                patient_id=patient.patient_id,
                token_number=f"P-{index:03}",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.ACTIVE,
            )

            visits.append(visit)

        db.add_all(visits)
        await db.flush()

        entries = []

        for index, visit in enumerate(visits, start=1):
            entries.append(
                QueueEntry(
                    visit_id=visit.visit_id,
                    dept_id=department.dept_id,
                    sequence_number=index,
                    priority=QueuePriority.NORMAL,
                    status=QueueEntryStatus.WAITING,
                )
            )

        db.add_all(entries)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id,
            next_limit=2,
        )

        assert len(display.next_tokens) == 2

        assert [
            token.token_number
            for token in display.next_tokens
        ] == [
            "P-001",
            "P-002",
        ]

    @pytest.mark.asyncio
    async def test_recent_tokens_respect_limit(
        self,
        db,
        patient_factory,
    ):
        department = Department(
            name="Laboratory",
            department_code="LAB",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        patients = [
            await patient_factory()
            for _ in range(4)
        ]

        visits = []

        for index, patient in enumerate(patients, start=1):
            visit = Visit(
                patient_id=patient.patient_id,
                token_number=f"L-{index:03}",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.COMPLETED,
            )

            visits.append(visit)

        db.add_all(visits)
        await db.flush()

        base_time = datetime.now(timezone.utc)

        entries = []

        for index, visit in enumerate(visits, start=1):
            entries.append(
                QueueEntry(
                    visit_id=visit.visit_id,
                    dept_id=department.dept_id,
                    sequence_number=index,
                    priority=QueuePriority.NORMAL,
                    status=QueueEntryStatus.COMPLETED,
                    completed_at=base_time + timedelta(minutes=index),
                )
            )

        db.add_all(entries)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id,
            recent_limit=2,
        )

        assert len(display.recent_tokens) == 2
    @pytest.mark.asyncio
    async def test_waiting_count_includes_all_waiting_entries(
        self,
        db,
        patient_factory,
    ):
        department = Department(
            name="Reception",
            department_code="REC",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        patients = [
            await patient_factory()
            for _ in range(5)
        ]

        visits = []

        for index, patient in enumerate(patients, start=1):
            visits.append(
                Visit(
                    patient_id=patient.patient_id,
                    token_number=f"A-{index:03}",
                    entry_type=EntryType.WALK_IN,
                    stage=VisitStage.ACTIVE,
                )
            )

        db.add_all(visits)
        await db.flush()

        entries = [
            QueueEntry(
                visit_id=visit.visit_id,
                dept_id=department.dept_id,
                sequence_number=index,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.WAITING,
            )
            for index, visit in enumerate(visits, start=1)
        ]

        db.add_all(entries)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id,
            next_limit=2,
        )

        assert len(display.next_tokens) == 2
        assert display.waiting_count == 5

class TestDisplayEdgeCases:

    @pytest.mark.asyncio
    async def test_recent_tokens_are_ordered_newest_first(
        self,
        db,
        patient_factory,
    ):
        department = Department(
            name="Pharmacy",
            department_code="PHARM",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        patients = [
            await patient_factory()
            for _ in range(3)
        ]

        visits = []

        for index, patient in enumerate(patients, start=1):
            visit = Visit(
                patient_id=patient.patient_id,
                token_number=f"P-{index:03}",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.COMPLETED,
            )
            visits.append(visit)

        db.add_all(visits)
        await db.flush()

        base_time = datetime.now(timezone.utc)

        entries = [
            QueueEntry(
                visit_id=visits[0].visit_id,
                dept_id=department.dept_id,
                sequence_number=1,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.COMPLETED,
                completed_at=base_time,
            ),
            QueueEntry(
                visit_id=visits[1].visit_id,
                dept_id=department.dept_id,
                sequence_number=2,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.COMPLETED,
                completed_at=base_time + timedelta(minutes=5),
            ),
            QueueEntry(
                visit_id=visits[2].visit_id,
                dept_id=department.dept_id,
                sequence_number=3,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.COMPLETED,
                completed_at=base_time + timedelta(minutes=10),
            ),
        ]

        db.add_all(entries)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        assert [
            token.token_number
            for token in display.recent_tokens
        ] == [
            "P-003",
            "P-002",
            "P-001",
        ]
    @pytest.mark.asyncio
    async def test_active_tokens_are_ordered_by_latest_call(
        self,
        db,
        patient_factory,
    ):
        department = Department(
            name="Reception",
            department_code="REC",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        patients = [
            await patient_factory()
            for _ in range(3)
        ]

        visits = []

        for index, patient in enumerate(patients, start=1):
            visit = Visit(
                patient_id=patient.patient_id,
                token_number=f"A-{index:03}",
                entry_type=EntryType.WALK_IN,
                stage=VisitStage.ACTIVE,
            )
            visits.append(visit)

        db.add_all(visits)
        await db.flush()

        base_time = datetime.now(timezone.utc)

        entries = [
            QueueEntry(
                visit_id=visits[0].visit_id,
                dept_id=department.dept_id,
                sequence_number=1,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.CALLED,
                called_at=base_time,
            ),
            QueueEntry(
                visit_id=visits[1].visit_id,
                dept_id=department.dept_id,
                sequence_number=2,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.IN_PROGRESS,
                called_at=base_time + timedelta(minutes=2),
            ),
            QueueEntry(
                visit_id=visits[2].visit_id,
                dept_id=department.dept_id,
                sequence_number=3,
                priority=QueuePriority.NORMAL,
                status=QueueEntryStatus.CALLED,
                called_at=base_time + timedelta(minutes=5),
            ),
        ]

        db.add_all(entries)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        assert [
            token.token_number
            for token in display.active_tokens
        ] == [
            "A-003",
            "A-002",
            "A-001",
        ]

    @pytest.mark.asyncio
    async def test_no_waiting_patients_returns_zero_estimated_wait(
        self,
        db,
    ):
        department = Department(
            name="Consultation",
            department_code="CONS",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        service = DisplayService(db)

        display = await service.get_department_display(
            department.dept_id
        )

        assert display.waiting_count == 0
        assert display.estimated_wait_minutes == 0

    @pytest.mark.asyncio
    async def test_estimated_wait_uses_queue_service(
        self,
        db,
        patient_factory,
    ):
        department = Department(
            name="Laboratory",
            department_code="LAB",
            type=DeptType.OPD,
            max_capacity=50,
            is_active=True,
        )

        db.add(department)
        await db.flush()

        patient = await patient_factory()

        visit = Visit(
            patient_id=patient.patient_id,
            token_number="L-001",
            entry_type=EntryType.WALK_IN,
            stage=VisitStage.ACTIVE,
        )

        db.add(visit)
        await db.flush()

        queue_entry = QueueEntry(
            visit_id=visit.visit_id,
            dept_id=department.dept_id,
            sequence_number=1,
            priority=QueuePriority.NORMAL,
            status=QueueEntryStatus.WAITING,
        )

        db.add(queue_entry)
        await db.flush()

        service = DisplayService(db)

        service.queue_service.get_estimated_wait_time = AsyncMock(
            return_value=17
        )

        result = await service._get_estimated_wait(
            department.dept_id
        )

        assert result == 17

        service.queue_service.get_estimated_wait_time.assert_awaited_once_with(
            queue_entry.queue_entry_id
        )

    @pytest.mark.asyncio
    async def test_unknown_department_uses_fallback_name(
        self,
        db,
    ):
        service = DisplayService(db)

        unknown_id = uuid4()

        display = await service.get_department_display(
            unknown_id
        )

        assert display.dept_id == unknown_id
        assert display.department_name == "Unknown Department"
        assert display.active_tokens == []
        assert display.next_tokens == []
        assert display.recent_tokens == []
        assert display.waiting_count == 0
        assert display.estimated_wait_minutes == 0

    @pytest.mark.asyncio
    async def test_snapshot_passes_limits_to_department_display(
        self,
        db,
    ):
        departments = [
            Department(
                name="Laboratory",
                department_code="LAB",
                type=DeptType.OPD,
                max_capacity=50,
                is_active=True,
            ),
            Department(
                name="Pharmacy",
                department_code="PHARM",
                type=DeptType.OPD,
                max_capacity=50,
                is_active=True,
            ),
        ]

        db.add_all(departments)
        await db.flush()

        service = DisplayService(db)

        original_method = service.get_department_display

        async def wrapped_method(
            dept_id,
            department_name=None,
            *,
            next_limit=3,
            recent_limit=3,
        ):
            assert next_limit == 2
            assert recent_limit == 1

            return await original_method(
                dept_id,
                department_name,
                next_limit=next_limit,
                recent_limit=recent_limit,
            )

        service.get_department_display = wrapped_method

        snapshot = await service.get_snapshot(
            next_limit=2,
            recent_limit=1,
        )

        assert len(snapshot.departments) == 2