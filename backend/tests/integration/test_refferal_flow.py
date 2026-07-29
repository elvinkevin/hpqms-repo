import pytest
from fastapi import HTTPException, status

from app.domain.models.models import (
    EntryType,
    QueueEntryStatus,
    QueuePriority,
    VisitStage,
)

from app.domain.schemas.schemas import (
    PatientCreate,
    VisitCreate,
)

from app.domain.services.patient_service import (
    PatientService,
)

from app.domain.services.visit_service import (
    VisitService,
)

from app.domain.services.routing_service import (
    RoutingService,
)


# ======================================================================
# REFERRAL ARRIVAL
# ======================================================================

class TestReferralArrival:

    @pytest.mark.asyncio
    async def test_referral_patient_registration(
        self,
        db,
    ):
        """
        Referral patient arrives at the hospital.

        Patient Registration
                ↓
        Referral Visit Created
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Samuel",
                last_name="Otieno",
                national_id="REF001001",
                phone="+254700555111",
                gender="MALE",
                date_of_birth="1988-04-15",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.REFERRAL,
                visit_reason="Referred for specialist consultation",
            )
        )

        assert patient.patient_id is not None

        assert visit.patient_id == patient.patient_id
        assert visit.entry_type == EntryType.REFERRAL
        assert visit.stage == VisitStage.ACTIVE
        assert visit.token_number is not None


# ======================================================================
# REFERRAL ROUTING
# ======================================================================

class TestReferralRouting:

    @pytest.mark.asyncio
    async def test_referral_patient_routed_to_reception(
        self,
        db,
        routing_departments,
    ):
        """
        Referral patients initially enter Reception.

        Referral
            ↓
        Reception

        They must not bypass Reception like appointments or emergencies.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        routing_service = RoutingService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Grace",
                last_name="Wanjiku",
                national_id="REF002002",
                phone="+254711555222",
                gender="FEMALE",
                date_of_birth="1991-09-20",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.REFERRAL,
                visit_reason="Specialist referral",
            )
        )

        queue_entry = await routing_service.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        await db.refresh(visit)

        # Must go to Reception
        assert (
            queue_entry.department_id
            == routing_departments["reception"].dept_id
        )

        # Must not bypass Reception
        assert (
            queue_entry.department_id
            != routing_departments["triage"].dept_id
        )

        assert (
            queue_entry.department_id
            != routing_departments["emergency"].dept_id
        )

        assert queue_entry.status == QueueEntryStatus.WAITING
        assert queue_entry.priority == QueuePriority.NORMAL

        # Visit should point to its active queue entry
        assert (
            visit.current_queue_entry_id
            == queue_entry.queue_entry_id
        )


# ======================================================================
# REFERRAL QUEUE PROGRESSION
# ======================================================================

class TestReferralQueueProgression:

    @pytest.mark.asyncio
    async def test_referral_queue_progression(
        self,
        db,
        routing_departments,
    ):
        """
        Referral queue lifecycle:

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

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Daniel",
                last_name="Kamau",
                national_id="REF003003",
                phone="+254722555333",
                gender="MALE",
                date_of_birth="1985-02-11",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.REFERRAL,
                visit_reason="Orthopedic referral",
            )
        )

        queue_entry = await routing_service.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        # Initial state
        assert queue_entry.status == QueueEntryStatus.WAITING
        assert queue_entry.priority == QueuePriority.NORMAL

        # Reception calls patient
        queue_entry = await routing_service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        assert queue_entry.status == QueueEntryStatus.CALLED

        # Reception starts handling patient
        queue_entry = await routing_service.start_queue_entry(
            queue_entry.queue_entry_id
        )

        assert queue_entry.status == QueueEntryStatus.IN_PROGRESS

        # Reception processing complete
        queue_entry = await routing_service.complete_queue_entry(
            queue_entry.queue_entry_id
        )

        assert queue_entry.status == QueueEntryStatus.COMPLETED


# ======================================================================
# REFERRAL VISIT COMPLETION
# ======================================================================

class TestReferralCompletion:

    @pytest.mark.asyncio
    async def test_referral_visit_completion(
        self,
        db,
        routing_departments,
    ):
        """
        Referral queue entry is completed and
        the overall visit is subsequently completed.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)
        routing_service = RoutingService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Mercy",
                last_name="Achieng",
                national_id="REF004004",
                phone="+254733555444",
                gender="FEMALE",
                date_of_birth="1993-11-05",
            )
        )

        visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.REFERRAL,
                visit_reason="Cardiology referral",
            )
        )

        queue_entry = await routing_service.dispatch_initial_kiosk_route(
            visit.visit_id
        )

        await routing_service.call_queue_entry(
            queue_entry.queue_entry_id
        )

        await routing_service.start_queue_entry(
            queue_entry.queue_entry_id
        )

        completed_queue = await routing_service.complete_queue_entry(
            queue_entry.queue_entry_id
        )

        assert completed_queue.status == QueueEntryStatus.COMPLETED

        completed_visit = await visit_service.complete_visit(
            visit.visit_id
        )

        assert completed_visit.stage == VisitStage.COMPLETED
        assert completed_visit.completed_at is not None


# ======================================================================
# DUPLICATE ACTIVE REFERRAL
# ======================================================================

class TestDuplicateReferralRejection:

    @pytest.mark.asyncio
    async def test_duplicate_active_referral_visit_rejected(
        self,
        db,
    ):
        """
        A patient cannot have two active visits simultaneously,
        even when both visits are referrals.
        """

        patient_service = PatientService(db)
        visit_service = VisitService(db)

        patient = await patient_service.register_standard_patient(
            PatientCreate(
                first_name="Brian",
                last_name="Kipchumba",
                national_id="REF005005",
                phone="+254744555555",
                gender="MALE",
                date_of_birth="1990-06-30",
            )
        )

        first_visit = await visit_service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.REFERRAL,
                visit_reason="First referral",
            )
        )

        assert first_visit.stage == VisitStage.ACTIVE

        with pytest.raises(HTTPException) as exc_info:

            await visit_service.start_visit(
                VisitCreate(
                    patient_id=patient.patient_id,
                    entry_type=EntryType.REFERRAL,
                    visit_reason="Duplicate referral",
                )
            )

        assert (
            exc_info.value.status_code
            == status.HTTP_409_CONFLICT
        )

        assert (
            exc_info.value.detail
            == "Patient already has an active visit."
        )