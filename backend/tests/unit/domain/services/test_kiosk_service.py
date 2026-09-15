from datetime import date, datetime, timezone
import uuid
import pytest
from fastapi import HTTPException

from app.domain.services.patient_service import PatientService
from app.domain.schemas.schemas import PatientCreate, PatientIdentifierType, PatientReconciliation, PatientUpdate,EmergencyPatientCreate
from app.domain.models.models import RegistrationStatus


@pytest.mark.asyncio
async def test_register_kiosk_patient_with_phone(db):
    service = PatientService(db)

    patient = await service.register_kiosk_patient(
        identifier="0712345678",
        identifier_type=PatientIdentifierType.PHONE,
    )

    assert patient.phone == "0712345678"
    assert patient.national_id is None
    assert patient.registration_status == RegistrationStatus.INCOMPLETE


@pytest.mark.asyncio
async def test_register_kiosk_patient_with_national_id(db):
    service = PatientService(db)

    patient = await service.register_kiosk_patient(
        identifier="12345678",
        identifier_type=PatientIdentifierType.NATIONAL_ID,
    )

    assert patient.national_id == "12345678"
    assert patient.phone is None
    assert patient.registration_status == RegistrationStatus.INCOMPLETE


@pytest.mark.asyncio
async def test_register_kiosk_patient_rejects_empty_identifier(db):
    service = PatientService(db)

    with pytest.raises(HTTPException) as exc:
        await service.register_kiosk_patient(
            identifier="   ",
            identifier_type=PatientIdentifierType.PHONE,
        )

    assert exc.value.status_code == 422
    assert "cannot be empty" in exc.value.detail

@pytest.mark.asyncio
async def test_register_kiosk_patient_rejects_invalid_phone_length(db):
    service = PatientService(db)

    with pytest.raises(HTTPException) as exc:
        await service.register_kiosk_patient(
            identifier="071234",
            identifier_type=PatientIdentifierType.PHONE,
        )

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_register_kiosk_patient_returns_existing_patient(
    db,
    patient_factory,
):
    existing = await patient_factory()
    existing.phone = "0712345678"
    existing.registration_status = RegistrationStatus.COMPLETE
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    service = PatientService(db)

    patient = await service.register_kiosk_patient(
        identifier="0712345678",
        identifier_type=PatientIdentifierType.PHONE,
    )

    assert patient.patient_id == existing.patient_id



@pytest.mark.asyncio
async def test_register_kiosk_patient_strips_identifier_whitespace(db):
    service = PatientService(db)

    patient = await service.register_kiosk_patient(
        identifier=" 0712345678 ",
        identifier_type=PatientIdentifierType.PHONE,
    )

    assert patient.phone == "0712345678"