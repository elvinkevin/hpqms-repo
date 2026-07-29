from datetime import date, datetime, timezone
import pytest
from fastapi import HTTPException
from app.domain.models.models import EntryType, QueueEntryStatus, QueuePriority, RegistrationStatus, VisitStage
from app.domain.schemas.schemas import EmergencyPatientCreate, PatientCreate, VisitCreate
from app.domain.services.patient_service import PatientService
from app.domain.services.routing_service import RoutingService
from app.domain.services.visit_service import VisitService


# ======================================================================
# EMERGENCY ARRIVAL WORKFLOWS
# ======================================================================

class TestEmergencyArrival:
    """
    Integration tests covering rapid emergency patient intake.

    These tests validate that HPQMS correctly supports emergency
    registration before complete demographic information is available.
    """

    @pytest.mark.asyncio
    async def test_rapid_emergency_intake(
        self,
        db,
    ):
        """
        Scenario:
            Conscious emergency patient arrives.

        Expected workflow:
            Rapid Intake
                ↓
            Temporary Patient Created
                ↓
            Temporary Identifier Assigned
                ↓
            Registration Status = INCOMPLETE
        """

        patient_service = PatientService(db)

        patient = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Jane",
                last_name="Doe",
                gender="FEMALE",
                estimated_age=30,
            )
        )

        assert patient.patient_id is not None
        assert patient.temporary_identifier.startswith("TEMP-")
        assert patient.registration_status == RegistrationStatus.INCOMPLETE

        assert patient.first_name == "Jane"
        assert patient.last_name == "Doe"

        assert patient.national_id is None
        assert patient.phone is None

        assert patient.estimated_age == 30

        assert patient.reconciled_at is None
        assert patient.reconciled_by is None

        assert patient.is_temporary is True


    @pytest.mark.asyncio
    async def test_unidentified_patient_intake(
        self,
        db,
    ):
        """
        Scenario:
            Unconscious / unidentified trauma patient arrives.

        Expected workflow:
            Anonymous Intake
                ↓
            Temporary Patient Created
                ↓
            Ready for Clinical Care
        """

        patient_service = PatientService(db)

        patient = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Unknown",
                last_name="Male",
                gender="UNKNOWN",
                estimated_age=45,
            )
        )

        assert patient.patient_id is not None

        assert patient.temporary_identifier.startswith("TEMP-")

        assert patient.registration_status == RegistrationStatus.INCOMPLETE

        assert patient.national_id is None
        assert patient.phone is None

        assert patient.reconciled_at is None
        assert patient.reconciled_by is None

        assert patient.is_temporary is True


    @pytest.mark.asyncio
    async def test_temporary_identifier_is_unique(
        self,
        db,
    ):
        """
        Scenario:
            Two emergency patients arrive consecutively.

        Business Rule:
            Every emergency intake receives a unique
            temporary identifier.
        """

        patient_service = PatientService(db)

        patient_one = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Patient",
                last_name="One",
                estimated_age=25,
            )
        )

        patient_two = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Patient",
                last_name="Two",
                estimated_age=40,
            )
        )

        assert (
            patient_one.temporary_identifier
            != patient_two.temporary_identifier
        )


    @pytest.mark.asyncio
    async def test_emergency_registration_accepts_partial_demographics(
        self,
        db,
    ):
        """
        Scenario:
            Only minimal information is available.

        Expected:
            Emergency registration should still succeed.
        """

        patient_service = PatientService(db)

        patient = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Unknown",
            )
        )

        assert patient.patient_id is not None

        assert patient.registration_status == RegistrationStatus.INCOMPLETE

        assert patient.temporary_identifier.startswith("TEMP-")


    @pytest.mark.asyncio
    async def test_emergency_registration_with_existing_identity_rejected(
        self,
        db,
    ):
        """
        Scenario:
            An emergency intake attempts to use a National ID
            that already belongs to another patient.

        Expected:
            Registration is rejected.
        """

        patient_service = PatientService(db)

        await patient_service.register_standard_patient(
            PatientCreate(
            first_name="Existing",
            last_name="Patient",
            national_id="12345678",
            phone="0712345678",
            gender="FEMALE",
            date_of_birth=date(1990, 1, 1),
        )
    )

        with pytest.raises(HTTPException) as exc:
            await patient_service.register_emergency_patient(
                EmergencyPatientCreate(
                    first_name="John",
                    last_name="Doe",
                    national_id="12345678",
                )
            )
        assert exc.value.status_code == 409

# ======================================================================
# EMERGENCY ROUTING WORKFLOWS
# ======================================================================

class TestEmergencyRouting:
    """
    Integration tests covering emergency routing and queue behaviour.

    Workflow:

    Emergency Arrival
            ↓
    Emergency Visit
            ↓
    Direct ER Dispatch
            ↓
    CRITICAL Queue
    """

    @pytest.mark.asyncio
    async def test_emergency_patient_routed_directly_to_emergency_department(
        self,
        db,
        routing_departments,
    ):
        """
        Scenario:
            Emergency patient arrives and is immediately routed
            to the Emergency Department.

        Expected:

            Emergency Patient
                    ↓
            Emergency Visit
                    ↓
            Dispatch
                    ↓
            Emergency Department
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        routing_service = RoutingService(db)

        patient = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Jane",
                last_name="Doe",
                gender="FEMALE",
                estimated_age=30,
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.EMERGENCY,
                visit_reason="Road Traffic Accident",
            )
        )

        queue_entry = await routing_service.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        await db.refresh(visit)

        assert visit.stage == VisitStage.ACTIVE
        assert visit.entry_type == EntryType.EMERGENCY

        assert queue_entry.visit_id == visit.visit_id
        assert queue_entry.department_id == routing_departments["emergency"].dept_id

        assert queue_entry.priority == QueuePriority.CRITICAL
        assert queue_entry.status == QueueEntryStatus.WAITING

        assert visit.current_queue_entry_id == queue_entry.queue_entry_id


    @pytest.mark.asyncio
    async def test_emergency_patient_bypasses_reception_and_triage(
        self,
        db,
        routing_departments,
    ):
        """
        Scenario:
            Emergency patients must never enter
            Reception or Triage.

        Expected:

            Emergency
                 │
                 ▼
          Emergency Department
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        routing_service = RoutingService(db)

        patient = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Unknown",
                estimated_age=45,
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.EMERGENCY,
                visit_reason="Cardiac Arrest",
            )
        )

        queue_entry = await routing_service.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        assert (
            queue_entry.department_id
            != routing_departments["reception"].dept_id
        )

        assert (
            queue_entry.department_id
            != routing_departments["triage"].dept_id
        )

        assert (
            queue_entry.department_id
            == routing_departments["emergency"].dept_id
        )


    @pytest.mark.asyncio
    async def test_emergency_queue_progression(
        self,
        db,
        routing_departments,
    ):
        """
        Scenario:

            Emergency patient progresses through
            the ER queue lifecycle.

        WAITING
            ↓
        CALLED
            ↓
        IN_PROGRESS
            ↓
        COMPLETED
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        routing_service = RoutingService(db)

        patient = await patient_service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="John",
                estimated_age=52,
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.EMERGENCY,
                visit_reason="Acute Chest Pain",
            )
        )

        queue_entry = await routing_service.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        assert queue_entry.status == QueueEntryStatus.WAITING
        assert queue_entry.priority == QueuePriority.CRITICAL

        called = await routing_service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        assert called.status == QueueEntryStatus.CALLED

        in_progress = await routing_service.start_queue_entry(
            queue_entry.queue_entry_id
        )

        assert in_progress.status == QueueEntryStatus.IN_PROGRESS

        completed = await routing_service.complete_queue_entry(
            queue_entry.queue_entry_id
        )

        assert completed.status == QueueEntryStatus.COMPLETED