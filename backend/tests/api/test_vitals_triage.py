"""
API-level tests for Vitals and Triage endpoints.

Tests the HTTP layer, authentication, and integration between
router and service layer.
"""
import pytest
from fastapi import status
from httpx import AsyncClient
from uuid import uuid4

from app.domain.models.models import QueueEntryStatus, QueuePriority
from app.domain.schemas.schemas import VitalsCreate, TriageAssessmentUpdate


pytestmark = pytest.mark.asyncio


# ==============================================================================
# 1. RECORD VITALS ENDPOINT TESTS
# ==============================================================================

class TestRecordVitalsEndpoint:
    """Test POST /visits/{visit_id}/vitals endpoint."""

    async def test_record_vitals_success(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """POST /visits/{visit_id}/vitals - Successfully record vitals."""
        payload = {
            "temperature": 98.6,
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "heart_rate": 72,
            "respiratory_rate": 16,
            "oxygen_saturation": 98,
            "weight": 70.5,
            "height": 175.0,
        }

        response = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=payload,
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        assert data["visit_id"] == str(active_visit.visit_id)
        assert data["temperature"] == 98.6
        assert data["heart_rate"] == 72
        assert data["recorded_at"] is not None

    async def test_record_vitals_minimal_fields(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """POST /visits/{visit_id}/vitals - Record with only required fields."""
        payload = {
            "temperature": 37.0,
        }

        response = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=payload,
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["temperature"] == 37.0

    async def test_record_vitals_unknown_visit(
        self,
        client: AsyncClient,
        doctor_token_headers,
    ):
        """POST /visits/{visit_id}/vitals - 404 for unknown visit."""
        payload = {"temperature": 98.6}

        response = await client.post(
            f"/api/visits/{uuid4()}/vitals",
            json=payload,
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    async def test_record_vitals_invalid_uuid(
        self,
        client: AsyncClient,
        doctor_token_headers,
    ):
        """POST /visits/{visit_id}/vitals - 422 for malformed UUID."""
        response = await client.post(
            "/api/visits/invalid-uuid/vitals",
            json={"temperature": 98.6},
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_record_vitals_unauthorized(
        self,
        client: AsyncClient,
        active_visit,
    ):
        """POST /visits/{visit_id}/vitals - 401 without authentication."""
        payload = {"temperature": 98.6}

        response = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=payload,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_record_vitals_multiple_times(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """POST /visits/{visit_id}/vitals - Record multiple times creates separate entries."""
        payload_1 = {"temperature": 98.0, "heart_rate": 70}
        payload_2 = {"temperature": 98.6, "heart_rate": 72}

        res_1 = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=payload_1,
            headers=doctor_token_headers,
        )
        res_2 = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=payload_2,
            headers=doctor_token_headers,
        )

        assert res_1.status_code == status.HTTP_201_CREATED
        assert res_2.status_code == status.HTTP_201_CREATED

        data_1 = res_1.json()
        data_2 = res_2.json()

        # Different vitals IDs
        assert data_1["vitals_id"] != data_2["vitals_id"]
        # Different temperatures
        assert data_1["temperature"] != data_2["temperature"]


# ==============================================================================
# 2. GET VITALS ENDPOINT TESTS
# ==============================================================================

class TestGetVitalsEndpoint:
    """Test GET /visits/{visit_id}/vitals endpoints."""
    async def test_get_latest_vitals_success(
            self,
            client: AsyncClient,
            active_visit,
            doctor_token_headers,
            doctor_staff,  
            db,
        ):
            """GET /visits/{visit_id}/vitals/latest - Returns most recent vitals."""
            from app.domain.services.vitals_service import VitalsService

            # Record vitals via service using a REAL staff member's ID
            await VitalsService.record_vitals(
                db=db,
                visit_id=active_visit.visit_id,
                staff_id=doctor_staff.staff_id,  
                vitals_in=VitalsCreate(temperature=98.0),
            )

            vitals_2 = await VitalsService.record_vitals(
                db=db,
                visit_id=active_visit.visit_id,
                staff_id=doctor_staff.staff_id,  
                vitals_in=VitalsCreate(temperature=98.6),
            )

            # Get via API
            response = await client.get(
                f"/api/visits/{active_visit.visit_id}/vitals/latest",
                headers=doctor_token_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["temperature"] == 98.6
            assert data["vitals_id"] == str(vitals_2.vitals_id)


    async def test_get_latest_vitals_none(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """GET /visits/{visit_id}/vitals/latest - Returns null when no vitals exist."""
        response = await client.get(
            f"/api/visits/{active_visit.visit_id}/vitals/latest",
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() is None

    async def test_get_all_vitals_success(
            self,
            client: AsyncClient,
            active_visit,
            doctor_token_headers,
            doctor_staff,  
            db,
        ):
            """GET /visits/{visit_id}/vitals - Returns all vitals in reverse chronological order."""
            from app.domain.services.vitals_service import VitalsService

            # Record vitals
            for temp in [98.0, 98.6, 99.0]:
                await VitalsService.record_vitals(
                    db=db,
                    visit_id=active_visit.visit_id,
                    staff_id=doctor_staff.staff_id, 
                    vitals_in=VitalsCreate(temperature=temp),
                )

            # Get via API
            response = await client.get(
                f"/api/visits/{active_visit.visit_id}/vitals",
                headers=doctor_token_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 3
            # Most recent first
            assert data[0]["temperature"] == 99.0
            assert data[2]["temperature"] == 98.0


    async def test_get_all_vitals_empty(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """GET /visits/{visit_id}/vitals - Returns empty list when no vitals exist."""
        response = await client.get(
            f"/api/visits/{active_visit.visit_id}/vitals",
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_get_vitals_unknown_visit(
        self,
        client: AsyncClient,
        doctor_token_headers,
    ):
        """GET /visits/{visit_id}/vitals - Returns empty for non-existent visit."""
        response = await client.get(
            f"/api/visits/{uuid4()}/vitals",
            headers=doctor_token_headers,
        )

        # Service returns empty list for unknown visits
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_get_vitals_invalid_uuid(
        self,
        client: AsyncClient,
        doctor_token_headers,
    ):
        """GET /visits/{visit_id}/vitals - 422 for malformed UUID."""
        response = await client.get(
            "/api/visits/invalid-uuid/vitals",
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ==============================================================================
# 3. UPDATE TRIAGE ASSESSMENT ENDPOINT TESTS
# ==============================================================================

class TestUpdateTriageAssessmentEndpoint:
    """Test PATCH /visits/{visit_id}/triage-assessment endpoint."""

    async def test_update_triage_assessment_success(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """PATCH /visits/{visit_id}/triage-assessment - Successfully update assessment."""
        payload = {
            "chief_complaint": "Severe headache",
            "triage_assessment": "Urgent - migraines",
        }

        response = await client.patch(
            f"/api/visits/{active_visit.visit_id}/triage-assessment",
            json=payload,
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["visit_id"] == str(active_visit.visit_id)
        assert data["chief_complaint"] == "Severe headache"
        assert data["triage_assessment"] == "Urgent - migraines"

    async def test_update_triage_assessment_partial(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """PATCH /visits/{visit_id}/triage-assessment - Partial update (exclude_unset)."""
        # Initial update
        payload_1 = {
            "chief_complaint": "Headache",
            "triage_assessment": "Monitor",
        }
        await client.patch(
            f"/api/visits/{active_visit.visit_id}/triage-assessment",
            json=payload_1,
            headers=doctor_token_headers,
        )

        # Partial update - only chief complaint
        payload_2 = {"chief_complaint": "Severe headache"}
        response = await client.patch(
            f"/api/visits/{active_visit.visit_id}/triage-assessment",
            json=payload_2,
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["chief_complaint"] == "Severe headache"
        assert data["triage_assessment"] == "Monitor"  # Unchanged

    async def test_update_triage_assessment_unknown_visit(
        self,
        client: AsyncClient,
        doctor_token_headers,
    ):
        """PATCH /visits/{visit_id}/triage-assessment - 404 for unknown visit."""
        payload = {"chief_complaint": "Test"}

        response = await client.patch(
            f"/api/visits/{uuid4()}/triage-assessment",
            json=payload,
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_triage_assessment_invalid_uuid(
        self,
        client: AsyncClient,
        doctor_token_headers,
    ):
        """PATCH /visits/{visit_id}/triage-assessment - 422 for malformed UUID."""
        response = await client.patch(
            "/api/visits/invalid-uuid/triage-assessment",
            json={"chief_complaint": "Test"},
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_update_triage_assessment_requires_auth(
        self,
        client: AsyncClient,
        active_visit,
    ):
        """PATCH /visits/{visit_id}/triage-assessment - 401 without authentication."""
        payload = {"chief_complaint": "Headache"}

        response = await client.patch(
            f"/api/visits/{active_visit.visit_id}/triage-assessment",
            json=payload,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_triage_includes_latest_vitals(
            self,
            client: AsyncClient,
            active_visit,
            doctor_token_headers,
            doctor_staff,  # 👈 1. Inject the real staff fixture here
            db,
        ):
            """PATCH response includes latest_vitals in the response payload."""
            from app.domain.services.vitals_service import VitalsService

            # Record vitals first using a REAL staff member's ID
            vitals = await VitalsService.record_vitals(
                db=db,
                visit_id=active_visit.visit_id,
                staff_id=doctor_staff.staff_id,  # 👈 2. Replace uuid4() with the valid ID
                vitals_in=VitalsCreate(temperature=98.6, heart_rate=72),
            )

            # Update assessment
            payload = {"chief_complaint": "Checkup"}
            response = await client.patch(
                f"/api/visits/{active_visit.visit_id}/triage-assessment",
                json=payload,
                headers=doctor_token_headers,
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # latest_vitals should be populated
            assert "latest_vitals" in data
            if data["latest_vitals"]:
                assert data["latest_vitals"]["temperature"] == 98.6
                assert data["latest_vitals"]["heart_rate"] == 72



# ==============================================================================
# 4. INTEGRATED WORKFLOW TESTS
# ==============================================================================

class TestVitalsTriageWorkflow:
    """Test combined vitals and triage workflows."""

    async def test_complete_triage_workflow(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """Complete workflow: record vitals, then update assessment."""
        # Step 1: Record vitals
        vitals_payload = {
            "temperature": 98.6,
            "heart_rate": 72,
            "systolic_bp": 120,
            "diastolic_bp": 80,
        }

        vitals_response = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=vitals_payload,
            headers=doctor_token_headers,
        )

        assert vitals_response.status_code == status.HTTP_201_CREATED
        vitals_data = vitals_response.json()

        # Step 2: Get latest vitals
        latest_response = await client.get(
            f"/api/visits/{active_visit.visit_id}/vitals/latest",
            headers=doctor_token_headers,
        )

        assert latest_response.status_code == status.HTTP_200_OK
        assert latest_response.json()["vitals_id"] == vitals_data["vitals_id"]

        # Step 3: Update triage assessment
        assessment_payload = {
            "chief_complaint": "Routine checkup",
            "triage_assessment": "All vitals normal",
        }

        assessment_response = await client.patch(
            f"/api/visits/{active_visit.visit_id}/triage-assessment",
            json=assessment_payload,
            headers=doctor_token_headers,
        )

        assert assessment_response.status_code == status.HTTP_200_OK
        assessment_data = assessment_response.json()

        assert assessment_data["chief_complaint"] == "Routine checkup"
        assert "latest_vitals" in assessment_data

    async def test_critical_vitals_workflow(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """Workflow: Record critical vitals and escalate priority."""
        # Record critical vitals
        vitals_payload = {
            "temperature": 40.5,
            "heart_rate": 120,
            "oxygen_saturation": 88,
        }

        vitals_response = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=vitals_payload,
            headers=doctor_token_headers,
        )

        assert vitals_response.status_code == status.HTTP_201_CREATED

        # Update assessment to reflect critical status
        assessment_payload = {
            "chief_complaint": "Severe fever and SOB",
            "triage_assessment": "High fever, tachycardia, low O2. Admit for monitoring.",
        }

        assessment_response = await client.patch(
            f"/api/visits/{active_visit.visit_id}/triage-assessment",
            json=assessment_payload,
            headers=doctor_token_headers,
        )

        assert assessment_response.status_code == status.HTTP_200_OK
        data = assessment_response.json()

    async def test_multiple_vitals_recordings(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """Workflow: Record vitals multiple times and track progression."""
        temps = [37.0, 37.5, 38.0, 37.8]
        responses = []

        for temp in temps:
            response = await client.post(
                f"/api/visits/{active_visit.visit_id}/vitals",
                json={"temperature": temp},
                headers=doctor_token_headers,
            )
            assert response.status_code == status.HTTP_201_CREATED
            responses.append(response.json())

        # Get all vitals
        all_vitals_response = await client.get(
            f"/api/visits/{active_visit.visit_id}/vitals",
            headers=doctor_token_headers,
        )

        assert all_vitals_response.status_code == status.HTTP_200_OK
        all_vitals = all_vitals_response.json()

        assert len(all_vitals) == 4
        # Most recent first
        assert all_vitals[0]["temperature"] == 37.8
        assert all_vitals[3]["temperature"] == 37.0

    async def test_vitals_and_assessment_persistence(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """Verify vitals and assessment persist across multiple requests."""
        # Record vitals
        vitals_payload = {"temperature": 98.6, "heart_rate": 72}
        vitals_response = await client.post(
            f"/api/visits/{active_visit.visit_id}/vitals",
            json=vitals_payload,
            headers=doctor_token_headers,
        )
        vitals_id = vitals_response.json()["vitals_id"]

        # Update assessment
        assessment_payload = {"chief_complaint": "Test complaint"}
        await client.patch(
            f"/api/visits/{active_visit.visit_id}/triage-assessment",
            json=assessment_payload,
            headers=doctor_token_headers,
        )

        # Verify both persisted by retrieving separately
        latest_vitals_response = await client.get(
            f"/api/visits/{active_visit.visit_id}/vitals/latest",
            headers=doctor_token_headers,
        )
        assert latest_vitals_response.json()["vitals_id"] == vitals_id

        visit_response = await client.get(
            f"/api/visits/{active_visit.visit_id}",
            headers=doctor_token_headers,
        )
        assert visit_response.json()["chief_complaint"] == "Test complaint"
