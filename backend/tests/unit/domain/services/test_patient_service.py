from datetime import date, datetime, timezone
import uuid
import pytest
from fastapi import HTTPException

from app.domain.services.patient_service import PatientService
from app.domain.schemas.schemas import PatientCreate, PatientReconciliation, PatientUpdate,EmergencyPatientCreate
from app.domain.models.models import RegistrationStatus


# NOTE: All @pytest.mark.asyncio decorators have been removed to stop loop deadlocks

# ------------------------------------------
# Test 1 — register_standard_patient a patient
# ------------------------------------------
async def test_register_patient(db):
    service = PatientService(db)
    patient = await service.register_standard_patient(
        PatientCreate(
            national_id="12345678",
            first_name="John",
            last_name="Doe",
            phone="0712345678",
            registration_status=RegistrationStatus.COMPLETE,
        )
    )
    assert patient.patient_id is not None
    assert patient.first_name == "John"
    assert patient.last_name == "Doe"
    assert patient.national_id == "12345678"



# -------------------------------------
# Test 2 — Duplicate National ID
# -------------------------------------
async def test_duplicate_national_id(db):
    service = PatientService(db)
    
    data = PatientCreate(
        national_id="12345678",
        first_name="John",
        last_name="Doe",
        phone="0712345678",
        registration_status=RegistrationStatus.COMPLETE,
    )
    
    # 1. register_standard_patient the first patient
    await service.register_standard_patient(data)

    # 2. Attempting to register_standard_patient the duplicate will trigger the exception instantly
    with pytest.raises(HTTPException) as exc:
        await service.register_standard_patient(
            PatientCreate(
                national_id="12345678",  # Duplicate ID
                first_name="Jane",
                last_name="Smith",
                phone="0799999999",
                registration_status=RegistrationStatus.COMPLETE,
            )
        )
        
    assert exc.value.status_code == 409



# -------------------------------
# Test 3 — Retrieve by ID
# -------------------------------
async def test_get_patient_by_id(db):
    service = PatientService(db)
    patient = await service.register_standard_patient(
        PatientCreate(
            national_id="11111111",
            first_name="Alice",
            last_name="Walker",
            phone="0700000001",
            registration_status=RegistrationStatus.COMPLETE,
        )
    )
    retrieved = await service.get_by_id(patient.patient_id)
    assert retrieved.patient_id == patient.patient_id


# --------------------------------
# Test 4 — Unknown patients
# --------------------------------
async def test_unknown_patient_returns_404(db):
    service = PatientService(db)
    with pytest.raises(HTTPException) as exc:
        await service.get_by_id(uuid.uuid4())
    assert exc.value.status_code == 404


# ---------------------------
# Test 5 — Search 
# ---------------------------
async def test_search_patient(db):
    service = PatientService(db)
    await service.register_standard_patient(
        PatientCreate(
            national_id="22222222",
            first_name="Kevin",
            last_name="Axel",
            phone="0700000002",
            registration_status=RegistrationStatus.COMPLETE,
        )
    )
    results = await service.search_patients("Kevin")
    assert len(results) == 1
    assert results[0].first_name == "Kevin"


# --------------------------------------
# Test 6 — Update
# --------------------------------------
async def test_update_patient(db):
    service = PatientService(db)
    patient = await service.register_standard_patient(
        PatientCreate(
            national_id="33333333",
            first_name="John",
            last_name="Doe",
            phone="0700000003",
            registration_status=RegistrationStatus.COMPLETE,
        )
    )
    updated = await service.update_patient(
        patient.patient_id,
        PatientUpdate(first_name="Johnny")
    )
    assert updated.first_name == "Johnny"


# -------------------------------
# Test 7 — Patient exists
# -------------------------------
async def test_patient_exists(db):
    service = PatientService(db)
    await service.register_standard_patient(
        PatientCreate(
            national_id="44444444",
            first_name="Mike",
            last_name="Jones",
            phone="0700000004",
            registration_status=RegistrationStatus.COMPLETE,
        )
    )
    assert await service.get_by_national_id("44444444")
    assert await service.get_by_phone("0700000004")


# ----------------------------
# Test 8 — Patient does not exist
# ----------------------------
async def test_patient_does_not_exist(db):
    service = PatientService(db)
    assert not await service.get_by_national_id("99999999")



# --------------------------------------------------
# Test 9 — Get by temporary identifier
# --------------------------------------------------
async def test_get_by_temporary_identifier(db):
    service = PatientService(db)
    # Register emergency patient (auto-generates temporary_identifier)
    patient = await service.register_emergency_patient(
        EmergencyPatientCreate(
            first_name="John",
            last_name="Doe",
            gender="Male",
            estimated_age=30,
        )
    )

    # Verify lookup succeeds using the generated badge
    retrieved = await service.get_by_temporary_identifier(patient.temporary_identifier)
    assert retrieved is not None
    assert retrieved.patient_id == patient.patient_id

    # Verify unknown temporary ID returns None
    missing = await service.get_by_temporary_identifier("TEMP-NONEXISTENT")
    assert missing is None


# --------------------------------------------------
# Test 10 — Find patient using temporary identifier
# --------------------------------------------------
async def test_find_patient_by_temporary_identifier(db):
    service = PatientService(db)
    patient = await service.register_emergency_patient(
        EmergencyPatientCreate(
            first_name="Jane",
            last_name="Doe",
            gender="Female",
            estimated_age=25,
        )
    )

    # find_patient should resolve via temporary_identifier fallback
    found = await service.find_patient(patient.temporary_identifier)
    assert found.patient_id == patient.patient_id


# --------------------------------------------------
# Test 11 — Search patients by temporary identifier
# --------------------------------------------------
async def test_search_patients_by_temporary_identifier(db):
    service = PatientService(db)
    patient = await service.register_emergency_patient(
        EmergencyPatientCreate(
            first_name="Emergency",
            last_name="Patient",
            gender="Unknown",
            estimated_age=50,
        )
    )

    # Search by the generated temporary identifier string
    results = await service.search_patients(patient.temporary_identifier)
    assert len(results) == 1
    assert results[0].temporary_identifier == patient.temporary_identifier

# --------------------------------------------------
# Test 12 — Emergency Patient Registration
# --------------------------------------------------
async def test_register_emergency_patient(db):
    service = PatientService(db)
    emergency_dto = EmergencyPatientCreate(
        first_name="John",
        last_name="Doe",
        gender="Male",
        estimated_age=35,
    )

    patient = await service.register_emergency_patient(emergency_dto)

    assert patient.patient_id is not None
    assert patient.temporary_identifier.startswith("TEMP-")
    assert patient.registration_status == RegistrationStatus.INCOMPLETE
    assert patient.is_temporary is True
    assert patient.estimated_age == 35


# --------------------------------------------------
# Test 13 — Reconcile Temporary Patient
# --------------------------------------------------
async def test_reconcile_patient(db, receptionist_staff):  # <--- Changed staff_user to receptionist_staff
    service = PatientService(db)

    # 1. Register emergency patient
    emergency_patient = await service.register_emergency_patient(
        EmergencyPatientCreate(
            first_name="John",
            last_name="Doe",
            estimated_age=40,
        )
    )

    # 2. Reconcile with verified demographic identity
    reconcile_dto = PatientReconciliation(
        national_id="99887766",
        first_name="RealJohn",
        last_name="Smith",
        phone="0711223344",
        date_of_birth=date(1984, 5, 12),
        gender="Male",
    )

    reconciled = await service.reconcile_patient(
        patient_id=emergency_patient.patient_id,
        reconcile_data=reconcile_dto,
        staff_id=receptionist_staff.staff_id,  # <--- Updated here
    )

    assert reconciled.registration_status == RegistrationStatus.COMPLETE
    assert reconciled.is_temporary is False
    assert reconciled.national_id == "99887766"
    assert reconciled.first_name == "RealJohn"
    assert reconciled.reconciled_by == receptionist_staff.staff_id  # <--- Updated here
    assert reconciled.reconciled_at is not None

#----------------------------------------------
# Test 14 — Prevent Double Reconciliation
# --------------------------------------------------
async def test_reconcile_already_completed_patient_raises_conflict(db, receptionist_staff):
    service = PatientService(db)

    # Register & Reconcile Emergency Patient
    patient = await service.register_emergency_patient(
        EmergencyPatientCreate(first_name="John", last_name="Doe", estimated_age=30)
    )
    
    reconcile_dto = PatientReconciliation(
        national_id="11223344",
        first_name="VerifiedJohn",
        last_name="Doe",
        phone="0722000111",
        date_of_birth=date(1996, 1, 1),
        gender="Male",
    )

    await service.reconcile_patient(
        patient_id=patient.patient_id,
        reconcile_data=reconcile_dto,
        staff_id=receptionist_staff.staff_id,
    )

    # Attempting to reconcile a second time should fail
    with pytest.raises(HTTPException) as exc_info:
        await service.reconcile_patient(
            patient_id=patient.patient_id,
            reconcile_data=reconcile_dto,
            staff_id=receptionist_staff.staff_id,
        )

    assert exc_info.value.status_code == 409
    assert "already COMPLETE" in exc_info.value.detail


# --------------------------------------------------
# Test 15 — Emergency Registration Validates Existing Identity
# --------------------------------------------------
async def test_register_emergency_patient_validates_supplied_identity(db):
    service = PatientService(db)

    # Register an existing patient with National ID
    await service.register_standard_patient(
        PatientCreate(
            national_id="87654321",
            first_name="Existing",
            last_name="Patient",
            phone="0712345678",
            date_of_birth=date(1990, 5, 20),
            gender="Female",
        )
    )

    # Registering Emergency Patient with the same National ID must fail
    with pytest.raises(HTTPException) as exc_info:
        await service.register_emergency_patient(
            EmergencyPatientCreate(
                first_name="Conscious",
                last_name="JohnDoe",
                national_id="87654321",
            )
        )

    assert exc_info.value.status_code == 409
    assert "National ID '87654321' already exists" in exc_info.value.detail


# ------------------------------------------------------------------------------
# Test 13 — Deactivate Patient
# ------------------------------------------------------------------------------

async def test_deactivate_patient(db, patient):
    service = PatientService(db)

    updated = await service.set_active_status(
        patient_id=patient.patient_id,
        is_active=False,
    )

    assert updated.is_active is False


# ------------------------------------------------------------------------------
# Test 14 — Reactivate Patient
# ------------------------------------------------------------------------------

async def test_reactivate_patient(db, patient_factory):
    # Call the factory to create a patient instance
    patient = await patient_factory()
    
    patient.is_active = False
    await db.flush()

    service = PatientService(db)

    updated = await service.set_active_status(
        patient_id=patient.patient_id,
        is_active=True,
    )
    
    assert updated.is_active is True


# ------------------------------------------------------------------------------
# Test 15 — Cannot Deactivate Patient With Active Visit
# ------------------------------------------------------------------------------

async def test_cannot_deactivate_patient_with_active_visit(
    db,
    active_visit,
):
    service = PatientService(db)

    with pytest.raises(HTTPException) as exc:
        await service.set_active_status(
            patient_id=active_visit.patient_id,
            is_active=False,
        )
    
    assert exc.value.status_code == 409  # Optional: verify exception status code


# ------------------------------------------------------------------------------
# Test 16 — Deactivate Unknown Patient
# ------------------------------------------------------------------------------

async def test_set_active_status_unknown_patient(db):
    service = PatientService(db)

    with pytest.raises(HTTPException) as exc:
        await service.set_active_status(
            patient_id=uuid.uuid4(),
            is_active=False,
        )

    assert exc.value.status_code == 404