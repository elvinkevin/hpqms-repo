import uuid

import pytest
from httpx import AsyncClient
from fastapi import status

from app.domain.models.models import Patient
from app.domain.services.patient_service import PatientService

pytestmark = pytest.mark.asyncio


# 1. Success Registration
async def test_create_patient_success(client: AsyncClient, receptionist_token_headers: dict):
    payload = {
        "first_name": "John",
        "last_name": "Doe",
        "national_id": "12345678",
        "phone": "+254712345678",
        "gender": "MALE",
        "date_of_birth": "1990-01-01",
    }
    response = await client.post(
        "/api/patients",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["first_name"] == "John"
    assert "patient_id" in data


# 2. Duplicate National ID
async def test_create_patient_duplicate_national_id(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    payload = {
        "first_name": "Jane",
        "last_name": "Doe",
        "national_id": existing_patient.national_id,  # Duplicate ID
        "phone": "+254799999999",
    }
    response = await client.post(
        "/api/patients",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT)


# 3. Duplicate Phone
async def test_create_patient_duplicate_phone(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    payload = {
        "first_name": "Jane",
        "last_name": "Doe",
        "national_id": "87654321",
        "phone": existing_patient.phone,  # Duplicate Phone
    }
    response = await client.post(
        "/api/patients",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT)


# 4. Validation Error (Short national_id triggers validator)
async def test_create_patient_validation_error(client: AsyncClient, receptionist_token_headers: dict):
    payload = {
        "first_name": "John",
        "last_name": "Doe",
        "national_id": "12345",  # Less than 6 chars triggers field_validator
    }
    response = await client.post(
        "/api/patients",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# 5. Unauthorized (No Token)
async def test_create_patient_unauthorized(client: AsyncClient):
    payload = {
        "first_name": "John",
        "last_name": "Doe",
        "national_id": "12345678",
    }
    response = await client.post("/api/patients", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# 6. Forbidden Role (Doctor trying to register patient)
async def test_create_patient_forbidden_role(client: AsyncClient, doctor_token_headers: dict):
    payload = {
        "first_name": "John",
        "last_name": "Doe",
        "national_id": "12345678",
    }
    response = await client.post(
        "/api/patients",
        json=payload,
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ── GROUP 2: PATIENT SEARCH & LOOKUPS ───────────────────────────────────

# 7. Find Patient by National ID
async def test_find_patient_by_national_id(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    response = await client.get(
        f"/api/patients/find/{existing_patient.national_id}",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["patient_id"] == str(existing_patient.patient_id)
    assert data["national_id"] == existing_patient.national_id


# 8. Find Patient by Phone Number
async def test_find_patient_by_phone(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    response = await client.get(
        f"/api/patients/find/{existing_patient.phone}",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["patient_id"] == str(existing_patient.patient_id)
    assert data["phone"] == existing_patient.phone


# 9. Find Patient Not Found
async def test_find_patient_not_found(
    client: AsyncClient, receptionist_token_headers: dict
):
    response = await client.get(
        "/api/patients/find/nonexistent_identifier_9999",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# 10. Multi-field Search (Query matching name, phone, or ID)
async def test_search_patients(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    response = await client.get(
        "/api/patients/search",
        params={"q": "Existing"},
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(p["patient_id"] == str(existing_patient.patient_id) for p in data)


# 11. Search Patients No Results
async def test_search_patients_empty_results(
    client: AsyncClient, receptionist_token_headers: dict
):
    response = await client.get(
        "/api/patients/search",
        params={"q": "NonExistentNameXYZ123"},
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


# ── GROUP 3: GET BY ID & UPDATE ───────────────────────────────────────────

# 12. Get Patient by UUID Success
async def test_get_patient_by_id_success(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    response = await client.get(
        f"/api/patients/{existing_patient.patient_id}",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["patient_id"] == str(existing_patient.patient_id)
    assert data["first_name"] == existing_patient.first_name


# 13. Get Patient by ID Not Found
async def test_get_patient_by_id_not_found(
    client: AsyncClient, receptionist_token_headers: dict
):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"/api/patients/{fake_uuid}",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# 14. Get Patient Invalid UUID Format
async def test_get_patient_by_id_invalid_uuid(
    client: AsyncClient, receptionist_token_headers: dict
):
    response = await client.get(
        "/api/patients/not-a-valid-uuid",
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# 15. Update Patient Details Success (Partial Update)
async def test_update_patient_success(
    client: AsyncClient, receptionist_token_headers: dict, existing_patient
):
    payload = {
        "allergies": "Penicillin",
        "blood_type": "O+",
    }
    response = await client.patch(
        f"/api/patients/{existing_patient.patient_id}",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["allergies"] == "Penicillin"
    assert data["blood_type"] == "O+"
    # Verify untouched fields remain intact
    assert data["first_name"] == existing_patient.first_name


# 16. Update Non-existent Patient
async def test_update_patient_not_found(
    client: AsyncClient, receptionist_token_headers: dict
):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    payload = {"first_name": "UpdatedName"}
    response = await client.patch(
        f"/api/patients/{fake_uuid}",
        json=payload,
        headers=receptionist_token_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND

# ------------------------------------------------------------------
# 2. EMERGENCY PATIENT INTAKE (JOHN DOE)
# ------------------------------------------------------------------

async def test_create_emergency_patient_success(client, receptionist_token_headers):
    payload = {
        "first_name": "John",
        "last_name": "Doe",
        "gender": "Male",
        "estimated_age": 35,
    }

    response = await client.post(
        "/api/patients/emergency",
        json=payload,
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["patient_id"] is not None
    assert data["registration_status"] == "INCOMPLETE"
    assert data["temporary_identifier"].startswith("TEMP-")
    assert data["estimated_age"] == 35


async def test_create_emergency_patient_allowed_roles(client, doctor_token_headers):
    """
    Verify ER Triage / Doctors can also perform emergency intake.
    """
    payload = {
        "first_name": "Unidentified",
        "last_name": "Trauma Patient",
        "gender": "Unknown",
        "estimated_age": 50,
    }

    response = await client.post(
        "/api/patients/emergency",
        json=payload,
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["temporary_identifier"].startswith("TEMP-")


async def test_create_emergency_patient_validates_supplied_identity(client, receptionist_token_headers):
    # 1. Register standard patient
    await client.post(
        "/api/patients",
        json={
            "first_name": "Existing",
            "last_name": "User",
            "national_id": "NAT-EXISTING",
            "phone": "0733112233",
            "gender": "Male",
        },
        headers=receptionist_token_headers,
    )

    # 2. Register emergency patient with conflicting supplied national_id
    response = await client.post(
        "/api/patients/emergency",
        json={
            "first_name": "ConsciousJohn",
            "last_name": "Doe",
            "national_id": "NAT-EXISTING",
        },
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "NAT-EXISTING" in response.json()["detail"]


# ------------------------------------------------------------------
# 3. IDENTITY RECONCILIATION
# ------------------------------------------------------------------

async def test_reconcile_emergency_patient_success(client, receptionist_token_headers):
    # 1. Create emergency patient
    emg_resp = await client.post(
        "/api/patients/emergency",
        json={"first_name": "John", "last_name": "Doe", "estimated_age": 40},
        headers=receptionist_token_headers,
    )
    patient_id = emg_resp.json()["patient_id"]
    temp_badge = emg_resp.json()["temporary_identifier"]

    # 2. Reconcile record
    reconcile_payload = {
        "first_name": "VerifiedJohn",
        "last_name": "Mwangi",
        "national_id": "NAT-88776655",
        "phone": "0799887766",
        "date_of_birth": "1986-04-12",
        "gender": "Male",
        "blood_type": "O+",
    }

    rec_resp = await client.patch(
        f"/api/patients/{patient_id}/reconcile",
        json=reconcile_payload,
        headers=receptionist_token_headers,
    )

    assert rec_resp.status_code == status.HTTP_200_OK
    data = rec_resp.json()
    assert data["registration_status"] == "COMPLETE"
    assert data["first_name"] == "VerifiedJohn"
    assert data["national_id"] == "NAT-88776655"
    assert data["temporary_identifier"] == temp_badge  # Retains history
    assert data["reconciled_at"] is not None


async def test_reconcile_already_completed_patient_raises_conflict(client, receptionist_token_headers):
    # 1. Create emergency patient
    emg_resp = await client.post(
        "/api/patients/emergency",
        json={"first_name": "Jane", "last_name": "Doe"},
        headers=receptionist_token_headers,
    )
    patient_id = emg_resp.json()["patient_id"]

    reconcile_payload = {
        "first_name": "Jane",
        "last_name": "Achieng",
        "national_id": "NAT-554433",
        "phone": "0712345999",
        "date_of_birth": "1994-09-20",
    }

    # 2. First reconciliation -> 200 OK
    res1 = await client.patch(
        f"/api/patients/{patient_id}/reconcile",
        json=reconcile_payload,
        headers=receptionist_token_headers,
    )
    assert res1.status_code == status.HTTP_200_OK

    # 3. Second reconciliation attempt -> 409 Conflict
    res2 = await client.patch(
        f"/api/patients/{patient_id}/reconcile",
        json=reconcile_payload,
        headers=receptionist_token_headers,
    )
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert "already COMPLETE" in res2.json()["detail"]

# ------------------------------------------------------------------
# 4. LOOKUPS & SEARCH
# ------------------------------------------------------------------

async def test_find_patient_by_temporary_badge(client, receptionist_token_headers):
    emg_resp = await client.post(
        "/api/patients/emergency",
        json={"first_name": "Badged", "last_name": "Patient"},
        headers=receptionist_token_headers,
    )
    temp_badge = emg_resp.json()["temporary_identifier"]
    patient_id = emg_resp.json()["patient_id"]

    # Endpoint lookup using find/{identifier}
    response = await client.get(
        f"/api/patients/find/{temp_badge}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["patient_id"] == patient_id


async def test_search_patients_by_temporary_identifier(client, receptionist_token_headers):
    emg_resp = await client.post(
        "/api/patients/emergency",
        json={"first_name": "Searchable", "last_name": "Doe"},
        headers=receptionist_token_headers,
    )
    temp_badge = emg_resp.json()["temporary_identifier"]

    response = await client.get(
        f"/api/patients/search?q={temp_badge}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    results = response.json()
    assert len(results) >= 1
    assert any(p["temporary_identifier"] == temp_badge for p in results)


# ------------------------------------------------------------------
# 5. SECURITY & ACCESS CONTROL
# ------------------------------------------------------------------

async def test_unauthenticated_requests_blocked(client):
    res_emergency = await client.post("/api/patients/emergency", json={"first_name": "John"})
    assert res_emergency.status_code == status.HTTP_401_UNAUTHORIZED

    res_reconcile = await client.patch(
        "/api/patients/00000000-0000-0000-0000-000000000000/reconcile",
        json={"first_name": "John", "last_name": "Doe", "national_id": "123", "phone": "123", "date_of_birth": "2000-01-01"},
    )
    assert res_reconcile.status_code == status.HTTP_401_UNAUTHORIZED



async def test_admin_can_deactivate_patient(
    client,
    db,
    patient,
    admin_headers,
):
    response = await client.patch(
        f"/api/patients/{patient.patient_id}/active-status",
        json={"is_active": False},
        headers=admin_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["patient_id"] == str(patient.patient_id)
    assert data["is_active"] is False



@pytest.mark.asyncio
async def test_deactivation_persists_to_database(
    client,
    db,
    patient,
    admin_headers,
):
    response = await client.patch(
        f"/api/patients/{patient.patient_id}/active-status",
        json={"is_active": False},
        headers=admin_headers,
    )

    assert response.status_code == 200

    # Safely refresh the specific instance asynchronously
    await db.refresh(patient)

    assert patient.is_active is False


async def test_admin_can_reactivate_patient(
    client,
    db,
    patient,
    admin_headers,
):
    patient.is_active = False
    await db.flush()

    response = await client.patch(
        f"/api/patients/{patient.patient_id}/active-status",
        json={"is_active": True},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True


import pytest
from fastapi import HTTPException, status

@pytest.mark.asyncio
async def test_cannot_deactivate_patient_with_active_visit(
    db,
    active_visit,
):
    service = PatientService(db)

    with pytest.raises(HTTPException) as exc_info:
        await service.set_active_status(
            patient_id=active_visit.patient_id,
            is_active=False,
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Cannot deactivate patient with an active visit."


async def test_receptionist_cannot_deactivate_patient(
    client,
    patient,
    receptionist_token_headers,
):
    response = await client.patch(
        f"/api/patients/{patient.patient_id}/active-status",
        json={"is_active": False},
        headers=receptionist_token_headers,
    )

    assert response.status_code in (401, 403)


async def test_deactivate_unknown_patient(
    client,
    admin_headers,
):
    patient_id = uuid.uuid4()

    response = await client.patch(
        f"/api/patients/{patient_id}/active-status",
        json={"is_active": False},
        headers=admin_headers,
    )

    assert response.status_code == 404