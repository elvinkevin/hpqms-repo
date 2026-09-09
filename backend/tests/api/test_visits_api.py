import pytest
from uuid import uuid4
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession)
from app.domain.models.models import QueueEntry, QueueEntryStatus

pytestmark = pytest.mark.asyncio


# ── GROUP 1: SUCCESS CASES ───────────────────────────────────────────────────

# 1. Create Visit (Standard)
async def test_create_visit_success(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    payload = {
        "patient_id": str(existing_patient.patient_id),
        "entry_type": "WALK_IN",
        "visit_reason": "Persistent headache for 2 days"
    }
    response = await client.post(
        "/api/visits",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["patient_id"] == str(existing_patient.patient_id)
    assert data["stage"] == "ACTIVE"
    assert data["visit_reason"] == payload["visit_reason"]


# 2. Appointment Visit
async def test_create_appointment_visit(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    payload = {
        "patient_id": str(existing_patient.patient_id),
        "entry_type": "APPOINTMENT",
        "visit_reason": "Scheduled annual checkup"
    }
    response = await client.post(
        "/api/visits",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["entry_type"] == "APPOINTMENT"


# 3. Emergency Visit
async def test_create_emergency_visit(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    payload = {
        "patient_id": str(existing_patient.patient_id),
        "entry_type": "EMERGENCY",
        "visit_reason": "Severe acute chest pain"
    }
    response = await client.post(
        "/api/visits",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["entry_type"] == "EMERGENCY"


# 4. Referral Visit
async def test_create_referral_visit(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    payload = {
        "patient_id": str(existing_patient.patient_id),
        "entry_type": "REFERRAL",
        "visit_reason": "Referred from St. Jude Clinic"
    }
    response = await client.post(
        "/api/visits",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["entry_type"] == "REFERRAL"


# 5. Retrieve Visit
async def test_get_visit_success(
    client: AsyncClient, receptionist_token_headers: dict, active_visit
):
    response = await client.get(
        f"/api/visits/{active_visit.visit_id}",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["visit_id"] == str(active_visit.visit_id)


async def test_complete_visit_success(
    client: AsyncClient, doctor_token_headers: dict, active_visit, db: AsyncSession
):
    # Fetch and complete any open queue entries tied to this visit
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id,
            QueueEntry.status.in_([QueueEntryStatus.WAITING, QueueEntryStatus.CALLED, QueueEntryStatus.IN_PROGRESS])
        )
    )
    for queue_entry in result.scalars().all():
        queue_entry.status = QueueEntryStatus.COMPLETED

    await db.commit()

    # Now request visit completion
    response = await client.patch(
        f"/api/visits/{active_visit.visit_id}/complete",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["stage"] == "COMPLETED"


# 7. Cancel Visit (Receptionist/Admin Role Required)
async def test_cancel_visit_success(
    client: AsyncClient, receptionist_token_headers: dict, active_visit
):
    response = await client.patch(
        f"/api/visits/{active_visit.visit_id}/cancel",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["stage"] == "CANCELLED"


# ── GROUP 2: FAILURE & EDGE CASES ──────────────────────────────────────────

# 8. Patient Not Found
async def test_create_visit_patient_not_found(
    client: AsyncClient, receptionist_token_headers: dict
):
    payload = {
        "patient_id": str(uuid4()),
        "entry_type": "WALK_IN",
        "visit_reason": "General consultation"
    }
    response = await client.post(
        "/api/visits",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# 9. Duplicate Active Visit (Service throws 409 CONFLICT)
async def test_create_duplicate_active_visit(
    client: AsyncClient, receptionist_token_headers: dict, active_visit
):
    payload = {
        "patient_id": str(active_visit.patient_id),
        "entry_type": "WALK_IN",
        "visit_reason": "Trying to open a 2nd active visit"
    }
    response = await client.post(
        "/api/visits",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_409_CONFLICT


# 10. Visit Not Found
async def test_get_visit_not_found(
    client: AsyncClient, receptionist_token_headers: dict
):
    response = await client.get(
        f"/api/visits/{uuid4()}",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# 11. Invalid UUID
async def test_get_visit_invalid_uuid(
    client: AsyncClient, receptionist_token_headers: dict
):
    response = await client.get(
        "/api/visits/not-a-valid-uuid",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# 12. Unauthorized (Missing Token)
async def test_visit_unauthorized(client: AsyncClient, active_visit):
    response = await client.get(f"/api/visits/{active_visit.visit_id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# 13. Forbidden Role (Nurse completing doctor-restricted visit)
async def test_complete_visit_forbidden_role(
    client: AsyncClient, receptionist_token_headers: dict, active_visit
):
    response = await client.patch(
        f"/api/visits/{active_visit.visit_id}/complete",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


# 14. Validation Error
async def test_create_visit_validation_error(
    client: AsyncClient, receptionist_token_headers: dict
):
    payload = {"visit_reason": "Missing patient_id and entry_type"}
    response = await client.post(
        "/api/visits",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# Append to tests/api/test_visits_api.py

@pytest.mark.asyncio
async def test_update_clinical_assessment_success(client: AsyncClient, doctor_token_headers, active_visit):
    payload = {
        "clinical_findings": "Patient exhibits mild fever and persistent cough.",
        "diagnosis": "Acute Bronchitis",
        "treatment_plan": "Rest, hydration, and prescribed antibiotics."
    }
    response = await client.patch(
        f"/api/visits/{active_visit.visit_id}/assessment",
        json=payload,
        headers=doctor_token_headers
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["clinical_findings"] == payload["clinical_findings"]
    assert data["diagnosis"] == payload["diagnosis"]
    assert data["treatment_plan"] == payload["treatment_plan"]


@pytest.mark.asyncio
async def test_update_clinical_assessment_forbidden_role(client: AsyncClient, receptionist_token_headers, active_visit):
    payload = {"diagnosis": "Unauthorized diagnosis entry"}
    response = await client.patch(
        f"/api/visits/{active_visit.visit_id}/assessment",
        json=payload,
        headers=receptionist_token_headers
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN