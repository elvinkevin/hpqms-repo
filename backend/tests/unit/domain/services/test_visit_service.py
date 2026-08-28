import uuid
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException

from app.domain.models.models import (
    EntryType,
    RegistrationStatus,
    VisitStage,
)
from app.domain.schemas.schemas import (
    PatientCreate,
    VisitCreate,
)
from app.domain.services.patient_service import PatientService
from app.domain.services.visit_service import VisitService


# ------------------------------------------------------------------------------
# Patient Fixture
# ------------------------------------------------------------------------------
@pytest.fixture
async def patient(db):
    patient_service = PatientService(db)
    return await patient_service.register_standard_patient(
        PatientCreate(
            national_id="12345678",
            first_name="Kevin",
            last_name="Axel",
            phone="0712345678",
            registration_status=RegistrationStatus.COMPLETE,
        )
    )


# ------------------------------------------------------------------------------
# Active Visit Fixture
# ------------------------------------------------------------------------------
@pytest.fixture
async def active_visit(db, patient):
    service = VisitService(db)
    service.token_service.generate_token = AsyncMock(return_value="W-001")

    return await service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="General Consultation",
        )
    )


# ------------------------------------------------------------------------------
# Complete Visit Fixture
# ------------------------------------------------------------------------------
@pytest.fixture
async def completed_visit(db, active_visit):
    service = VisitService(db)
    return await service.complete_visit(active_visit.visit_id)


# ------------------------------------------------------------------------------
# Test 1 — Start Visit Successfully
# ------------------------------------------------------------------------------

async def test_start_visit(db, patient):
    service = VisitService(db)
    service.token_service.generate_token = AsyncMock(return_value="W-001")

    visit = await service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="General Consultation",
        )
    )

    assert visit.patient_id == patient.patient_id
    assert visit.token_number == "W-001"
    assert visit.entry_type == EntryType.WALK_IN
    assert visit.stage == VisitStage.ACTIVE


# ------------------------------------------------------------------------------
# Test 2 — Start Visit Unknown Patient
# ------------------------------------------------------------------------------

async def test_start_visit_unknown_patient(db):
    service = VisitService(db)
    service.token_service.generate_token = AsyncMock(return_value="W-001")

    with pytest.raises(HTTPException) as exc:
        await service.start_visit(
            VisitCreate(
                patient_id=uuid.uuid4(),
                entry_type=EntryType.WALK_IN,
                visit_reason="Consultation",
            )
        )

    assert exc.value.status_code == 404


# ------------------------------------------------------------------------------
# Test 3 — Duplicate Active Visit
# ------------------------------------------------------------------------------

async def test_duplicate_active_visit(db, patient):
    service = VisitService(db)
    service.token_service.generate_token = AsyncMock(return_value="W-001")

    await service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="General Consultation",
        )
    )

    with pytest.raises(HTTPException) as exc:
        await service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="Second Visit",
            )
        )

    assert exc.value.status_code == 409


# ------------------------------------------------------------------------------
# Test 4 — Get Visit
# ------------------------------------------------------------------------------

async def test_get_visit(db, active_visit):
    service = VisitService(db)
    visit = await service.get_visit(active_visit.visit_id)
    assert visit.visit_id == active_visit.visit_id


# ------------------------------------------------------------------------------
# Test 5 — Unknown Visit
# ------------------------------------------------------------------------------

async def test_unknown_visit_returns_404(db):
    service = VisitService(db)
    with pytest.raises(HTTPException) as exc:
        await service.get_visit(uuid.uuid4())

    assert exc.value.status_code == 404


# ------------------------------------------------------------------------------
# Test 6 — Get Active Visit
# ------------------------------------------------------------------------------

async def test_get_active_visit(db, patient, active_visit):
    service = VisitService(db)
    visit = await service.get_active_visit(patient.patient_id)
    assert visit.visit_id == active_visit.visit_id


# ------------------------------------------------------------------------------
# Test 7 — No Active Visit
# ------------------------------------------------------------------------------

async def test_no_active_visit_returns_none(db, patient):
    service = VisitService(db)
    visit = await service.get_active_visit(patient.patient_id)
    assert visit is None


# ------------------------------------------------------------------------------
# Test 8 — Complete Visit
# ------------------------------------------------------------------------------

async def test_complete_visit(db, active_visit):
    service = VisitService(db)
    visit = await service.complete_visit(active_visit.visit_id)
    assert visit.stage == VisitStage.COMPLETED


# ------------------------------------------------------------------------------
# Test 9 — Cancel Visit
# ------------------------------------------------------------------------------

async def test_cancel_visit(db, active_visit):
    service = VisitService(db)
    visit = await service.cancel_visit(active_visit.visit_id)
    assert visit.stage == VisitStage.CANCELLED


# ------------------------------------------------------------------------------
# Test 10 — Completion Timestamp
# ------------------------------------------------------------------------------

async def test_completed_visit_sets_completed_at(db, active_visit):
    service = VisitService(db)
    visit = await service.complete_visit(active_visit.visit_id)
    assert visit.completed_at is not None


# ------------------------------------------------------------------------------
# Test 11 — Cancellation Timestamp
# ------------------------------------------------------------------------------

async def test_cancelled_visit_sets_completed_at(db, active_visit):
    service = VisitService(db)
    visit = await service.cancel_visit(active_visit.visit_id)
    assert visit.completed_at is not None


# ------------------------------------------------------------------------------
# Test 12 — Complete Unknown Visit
# ------------------------------------------------------------------------------

async def test_complete_unknown_visit_returns_404(db):
    service = VisitService(db)
    with pytest.raises(HTTPException) as exc:
        await service.complete_visit(uuid.uuid4())

    assert exc.value.status_code == 404


# ------------------------------------------------------------------------------
# Test 17 — Inactive Patient Cannot Start Visit
# ------------------------------------------------------------------------------

async def test_inactive_patient_cannot_start_visit(db, patient):
    patient.is_active = False
    await db.flush()

    service = VisitService(db)
    service.token_service.generate_token = AsyncMock(
        return_value="W-001"
    )

    with pytest.raises(HTTPException) as exc:
        await service.start_visit(
            VisitCreate(
                patient_id=patient.patient_id,
                entry_type=EntryType.WALK_IN,
                visit_reason="General Consultation",
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Patient record is inactive."


# ------------------------------------------------------------------------------
# Test 18 — Completing Visit Does Not Deactivate Patient
# ------------------------------------------------------------------------------

async def test_completing_visit_does_not_deactivate_patient(
    db,
    patient,
    active_visit,
):
    service = VisitService(db)

    visit = await service.complete_visit(
        active_visit.visit_id
    )

    assert visit.stage == VisitStage.COMPLETED
    assert patient.is_active is True




async def test_patient_can_start_new_visit_after_previous_visit_completed(
    db,
    patient,
):
    service = VisitService(db)

    service.token_service.generate_token = AsyncMock(
        side_effect=["W-001", "W-002"]
    )

    first_visit = await service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="First visit",
        )
    )

    await service.complete_visit(first_visit.visit_id)

    second_visit = await service.start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Return visit",
        )
    )

    assert first_visit.stage == VisitStage.COMPLETED
    assert second_visit.stage == VisitStage.ACTIVE
    assert second_visit.patient_id == patient.patient_id
    assert second_visit.token_number == "W-002"