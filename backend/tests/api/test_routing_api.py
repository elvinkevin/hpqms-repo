from uuid import uuid4
import pytest
import pytest_asyncio
from datetime import datetime
from fastapi import status
from httpx import AsyncClient
import os

from app.domain.models.models import (
    QueueEntry,
    VisitStage,
    EntryType,
    Department,
    DeptType,
    QueueEntryStatus,
    StaffRole,
    Visit,
    Patient,
    RegistrationStatus,
)
from app.core.security import create_access_token
from app.domain.models.models import Staff
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession)

from tests.conftest import make_headers

pytestmark = pytest.mark.asyncio

from uuid import uuid4
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select, delete

from app.domain.models.models import (
    QueueEntry,
    VisitStage,
    EntryType,
    QueueEntryStatus,
    StaffRole,
)
from app.domain.schemas.schemas import TransferReason


pytestmark = pytest.mark.asyncio


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 1: KIOSK DISPATCH
# ══════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def new_visit(db, existing_patient):
    from app.domain.models.models import Visit, VisitStage, EntryType
    visit = Visit(
        visit_id=uuid4(),
        patient_id=existing_patient.patient_id,
        token_number="W-102",
        entry_type=EntryType.WALK_IN,
        visit_reason="Routine Checkup",
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return visit

class TestKioskDispatch:
    """
    Test the initial patient routing from kiosk via dispatch endpoint.
    
    Endpoint: POST /api/routing/dispatch/{visit_id}
    
    Requires: X-Kiosk-API-Key header
    """

    async def test_dispatch_walk_in_routes_to_reception(
        self,
        client: AsyncClient,
        db,
        new_visit,
        setup_departments,
    ):
        """Walk-in patients should be routed to RECEPTION department."""
        # Arrange: Set visit type to WALK_IN
        new_visit.entry_type = EntryType.WALK_IN
        await db.commit()
        await db.refresh(new_visit)

        # Act
        response = await client.post(
            f"/api/routing/dispatch/{new_visit.visit_id}",
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED

        reception_dept = setup_departments["RECEPTION"]
        data = response.json()
        assert data["dept_id"] == str(reception_dept.dept_id)
        assert data["status"] == "WAITING"

    async def test_dispatch_appointment_routes_to_triage(
        self,
        client: AsyncClient,
        db,
        new_visit,
        setup_departments,
    ):
        """Appointment patients should bypass reception and go directly to TRIAGE."""
        # Arrange
        new_visit.entry_type = EntryType.APPOINTMENT
        await db.commit()
        await db.refresh(new_visit)

        # Act
        response = await client.post(
            f"/api/routing/dispatch/{new_visit.visit_id}",
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["visit_id"] == str(new_visit.visit_id)
        assert data["dept_id"] == str(setup_departments["TRIAGE"].dept_id)

    async def test_dispatch_emergency_routes_to_emergency(
        self,
        client: AsyncClient,
        db,
        new_visit,
        setup_departments,
    ):
        """Emergency patients should bypass all departments and route to EMERGENCY."""
        # Arrange
        new_visit.entry_type = EntryType.EMERGENCY
        await db.commit()
        await db.refresh(new_visit)

        # Act
        response = await client.post(
            f"/api/routing/dispatch/{new_visit.visit_id}",
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["visit_id"] == str(new_visit.visit_id)
        assert data["dept_id"] == str(setup_departments["EMERGENCY"].dept_id)
        # Emergency patients get CRITICAL priority
        assert data["priority"] == "CRITICAL"

    async def test_dispatch_referral_routes_to_reception(
        self,
        client: AsyncClient,
        db,
        new_visit,
        setup_departments,
    ):
        """Referral patients should follow standard reception workflow."""
        # Arrange
        new_visit.entry_type = EntryType.REFERRAL
        await db.commit()
        await db.refresh(new_visit)

        # Act
        response = await client.post(
            f"/api/routing/dispatch/{new_visit.visit_id}",
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["visit_id"] == str(new_visit.visit_id)
        assert data["dept_id"] == str(setup_departments["RECEPTION"].dept_id)

    async def test_dispatch_visit_not_found(
        self,
        client: AsyncClient,
    ):
        """POST /api/routing/dispatch/{visit_id} - 404 for unknown visit_id."""
        # Act
        response = await client.post(f"/api/routing/dispatch/{uuid4()}")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_dispatch_invalid_uuid(
        self,
        client: AsyncClient,
    ):
        """POST /api/routing/dispatch/{visit_id} - 422 for malformed UUID."""
        # Act
        response = await client.post("/api/routing/dispatch/invalid-uuid-format")

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_dispatch_completed_visit_fails(
        self,
        client: AsyncClient,
        db: AsyncSession,
        new_visit,
    ):
        """POST /api/routing/dispatch/{visit_id} - 409 Conflict for non-active visit."""
        # 1. Arrange: Update stage and sync with DB session
        new_visit.stage = VisitStage.COMPLETED
        db.add(new_visit)
        await db.commit()
        await db.refresh(new_visit)

        # 2. Act: Kiosk key is automatically injected by the client fixture
        response = await client.post(f"/api/routing/dispatch/{new_visit.visit_id}")

        # 3. Assert
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "active" in response.json()["detail"].lower()

    async def test_dispatch_rejects_invalid_kiosk_api_key(
        self,
        client: AsyncClient,
    ):
        """Kiosk dispatch is unavailable without the managed-device secret."""
        # Act
        response = await client.post(
            f"/api/routing/dispatch/{uuid4()}",
            headers={"X-Kiosk-API-Key": "invalid-key"},
        )

        # Assert
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 2: TRANSFER BETWEEN DEPARTMENTS
# ══════════════════════════════════════════════════════════════════════════════


class TestPatientTransfer:
    """
    Test patient transfers between departments.
    
    Endpoint: POST /api/routing/{visit_id}/transfer
    
    Requires: Authentication + Authorized Role
    """

    async def test_transfer_patient_success(
        self,
        client: AsyncClient,
        db: AsyncSession,
        active_visit,
        setup_departments,
        doctor_staff,
    ):
        """A doctor transfers an in-progress patient to another department."""
        from app.domain.models.models import QueueEntry

        # 1. Arrange: Fetch and start the active queue entry
        result = await db.execute(
            select(QueueEntry).where(
                QueueEntry.visit_id == active_visit.visit_id,
                QueueEntry.status == QueueEntryStatus.WAITING,
            )
        )
        current_entry = result.scalar_one()

        # 2. Update doctor's department to match the patient's current department
        doctor_staff.dept_id = current_entry.dept_id
        current_entry.status = QueueEntryStatus.IN_PROGRESS
        current_entry.assigned_staff_id = doctor_staff.staff_id

        db.add(doctor_staff)
        db.add(current_entry)
        await db.commit()

        # 3. Generate token headers with updated doctor_staff claims
        headers = make_headers(doctor_staff)

        target_department = setup_departments["CONSULT"]

        payload = {
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Patient requires further clinical assessment.",
        }

        # 4. Act
        response = await client.post(
            f"/api/routing/{active_visit.visit_id}/transfer",
            json=payload,
            headers=headers,
        )

        # 5. Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["visit_id"] == str(active_visit.visit_id)
        assert data["dept_id"] == str(target_department.dept_id)
        assert data["status"] == "WAITING"
        assert data["priority"] == "NORMAL"
        assert data["notes"] == "Patient requires further clinical assessment."

        # Verify old entry is completed
        await db.refresh(current_entry)
        assert current_entry.status == QueueEntryStatus.COMPLETED

        # Verify visit remains active
        await db.refresh(active_visit)
        assert active_visit.stage == VisitStage.ACTIVE

    async def test_transfer_waiting_patient_rejected(
        self,
        client: AsyncClient,
        db,
        active_visit,
        setup_departments,
        doctor_token_headers,
    ):
        """
        A patient must be actively in an encounter before being transferred.
        Cannot transfer from WAITING status.
        """
        from app.domain.models.models import QueueEntry

        # Arrange
        result = await db.execute(
            select(QueueEntry).where(
                QueueEntry.visit_id == active_visit.visit_id,
                QueueEntry.status == QueueEntryStatus.WAITING,
            )
        )
        current_entry = result.scalar_one()

        target_department = setup_departments["CONSULT"]

        payload = {
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Transfer attempt.",
        }

        # Act
        response = await client.post(
            f"/api/routing/{active_visit.visit_id}/transfer",
            json=payload,
            headers=doctor_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT
        detail = response.json()["detail"].lower()
        assert "in-progress" in detail or "started" in detail

    async def test_transfer_to_same_department_rejected(
        self,
        client: AsyncClient,
        db,
        active_visit,
        setup_departments,
        doctor_token_headers,
    ):
        """
        A patient cannot be transferred to the department they are
        already being served in.
        """
        from app.domain.models.models import QueueEntry

        # Arrange: Fetch and transition queue entry to IN_PROGRESS
        result = await db.execute(
            select(QueueEntry).where(
                QueueEntry.visit_id == active_visit.visit_id,
                QueueEntry.status == QueueEntryStatus.WAITING,
            )
        )
        current_entry = result.scalar_one()

        current_entry.status = QueueEntryStatus.IN_PROGRESS
        await db.commit()

        # Payload targeting the same department
        payload = {
            "target_dept_id": str(current_entry.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Invalid same-department transfer.",
        }

        # Act
        response = await client.post(
            f"/api/routing/{active_visit.visit_id}/transfer",
            json=payload,
            headers=doctor_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT
        assert (
            response.json()["detail"]
            == "Patient is already queued in the target department."
        )

    async def test_transfer_to_inactive_department_rejected(
        self,
        client: AsyncClient,
        db,
        active_visit,
        setup_departments,
        doctor_token_headers,
    ):
        """Transfers to inactive departments must be rejected."""
        from app.domain.models.models import QueueEntry

        # Arrange
        result = await db.execute(
            select(QueueEntry).where(
                QueueEntry.visit_id == active_visit.visit_id,
                QueueEntry.status == QueueEntryStatus.WAITING,
            )
        )
        current_entry = result.scalar_one()
        current_entry.status = QueueEntryStatus.IN_PROGRESS

        target_department = setup_departments["CONSULT"]
        target_department.is_active = False

        await db.commit()

        payload = {
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Transfer to inactive department.",
        }

        # Act
        response = await client.post(
            f"/api/routing/{active_visit.visit_id}/transfer",
            json=payload,
            headers=doctor_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        detail = response.json()["detail"].lower()
        assert "inactive" in detail or "does not exist" in detail

    async def test_transfer_critical_requires_notes(
        self,
        client: AsyncClient,
        db,
        active_visit,
        setup_departments,
        doctor_token_headers,
    ):
        """CRITICAL priority transfers require clinical justification notes."""
        from app.domain.models.models import QueueEntry

        # Arrange
        result = await db.execute(
            select(QueueEntry).where(
                QueueEntry.visit_id == active_visit.visit_id,
            )
        )
        current_entry = result.scalar_one()
        current_entry.status = QueueEntryStatus.IN_PROGRESS
        await db.commit()

        target_department = setup_departments["CONSULT"]

        # Attempt transfer with CRITICAL priority but no notes
        payload = {
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "CRITICAL",
            "notes": None,
        }

        # Act
        response = await client.post(
            f"/api/routing/{active_visit.visit_id}/transfer",
            json=payload,
            headers=doctor_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Convert the validation error list to a string or inspect error messages directly
        errors = response.json()["detail"]
        error_messages = [err.get("msg", "").lower() for err in errors]

        assert any("notes are required when priority is critical" in msg for msg in error_messages)

    async def test_transfer_requires_authentication(
        self,
        client: AsyncClient,
        active_visit,
        setup_departments,
    ):
        """An unauthenticated client cannot transfer a patient."""
        target_department = setup_departments["CONSULT"]

        payload = {
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Unauthorized transfer attempt.",
        }

        # Act
        response = await client.post(
            f"/api/routing/{active_visit.visit_id}/transfer",
            json=payload,
        )

        # Assert
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    async def test_transfer_forbidden_role(
        self,
        client,
        db,
        active_visit,
        queue_entry,
        admin_headers,
        setup_departments,
    ):
        """Non-medical staff cannot transfer patients (ADMIN restricted)."""
        target = setup_departments["CONSULT"]
        
        queue_entry.status = QueueEntryStatus.IN_PROGRESS
        await db.commit()
    
        payload = {
            "target_dept_id": str(target.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
        }

        # Act
        response = await client.post(
            f"/api/routing/{active_visit.visit_id}/transfer",
            json=payload,
            headers=admin_headers,
        )

        # Assert: ADMIN role IS allowed in the corrected router
        # If your actual requirement is to restrict ADMIN, change the router dependency
        assert response.status_code == status.HTTP_403_FORBIDDEN


# # ══════════════════════════════════════════════════════════════════════════════
# # GROUP 3: DEPRECATED /move/ ENDPOINT (backward compatibility)
# # ══════════════════════════════════════════════════════════════════════════════


# class TestMovePatientDeprecated:
#     """
#     Test the deprecated /move/ endpoint for backward compatibility.
    
#     Endpoint: POST /api/routing/move/{visit_id}
    
#       This is deprecated. Use POST /api/routing/{visit_id}/transfer instead.
#     """

#     async def test_move_patient_success(
#         self,
#         client,
#         db,
#         active_visit,
#         queue_entry,
#         doctor_staff,
#         doctor_token_headers,
#         setup_departments,
#     ):
#         """Deprecated move endpoint should still work for backward compatibility."""
#         # Arrange
#         queue_entry.status = QueueEntryStatus.IN_PROGRESS
#         queue_entry.assigned_staff_id = doctor_staff.staff_id
#         await db.commit()

#         target_dept = setup_departments["TRIAGE"]

#         payload = {
#             "target_dept_id": str(target_dept.dept_id),
#             "priority": "NORMAL",
#             "notes": "Transferring to triage",
#         }

#         # Act
#         response = await client.post(
#             f"/api/routing/move/{active_visit.visit_id}",
#             json=payload,
#             headers=doctor_token_headers,
#         )

#         # Assert
#         assert response.status_code == status.HTTP_200_OK

#         data = response.json()

#         assert data["dept_id"] == str(target_dept.dept_id)
#         assert data["visit_id"] == str(active_visit.visit_id)
#         assert data["status"] == "WAITING"
#         assert data["priority"] == "NORMAL"
#         assert data["notes"] == "Transferring to triage"

#     async def test_move_patient_inactive_department(
#         self, client: AsyncClient, db, active_visit, queue_entry, doctor_token_headers, setup_departments
#     ):
#         """POST /api/routing/move/{visit_id} - 400 for inactive target department."""
#         queue_entry.status = QueueEntryStatus.IN_PROGRESS
#         target_dept = setup_departments["TRIAGE"]
#         target_dept.is_active = False
#         await db.commit()

#         payload = {"target_dept_id": str(target_dept.dept_id)}

#         response = await client.post(
#             f"/api/routing/move/{active_visit.visit_id}", json=payload, headers=doctor_token_headers
#         )
#         assert response.status_code == status.HTTP_400_BAD_REQUEST

#     async def test_move_patient_visit_not_found(
#         self, client: AsyncClient, doctor_token_headers, setup_departments
#     ):
#         """POST /api/routing/move/{visit_id} - 404 for unknown visit_id."""
#         target_dept = setup_departments["TRIAGE"]
#         payload = {"target_dept_id": str(target_dept.dept_id)}

#         response = await client.post(
#             f"/api/routing/move/{uuid4()}", json=payload, headers=doctor_token_headers
#         )
#         assert response.status_code == status.HTTP_404_NOT_FOUND

#     async def test_move_patient_invalid_uuid(self, client: AsyncClient, doctor_token_headers):
#         """POST /api/routing/move/{visit_id} - 422 for malformed UUID."""
#         response = await client.post(
#             "/api/routing/move/invalid-uuid-format", json={}, headers=doctor_token_headers
#         )
#         assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

#     async def test_move_patient_token_preservation(
#         self,
#         client: AsyncClient,
#         db,
#         active_visit,
#         queue_entry,
#         doctor_staff,
#         doctor_token_headers,
#         setup_departments,
#     ):
#         """Verify token number is preserved when patient moves."""
#         queue_entry.status = QueueEntryStatus.IN_PROGRESS
#         queue_entry.assigned_staff_id = doctor_staff.staff_id

#         old_token = active_visit.token_number

#         await db.commit()

#         target_dept = setup_departments["TRIAGE"]

#         response = await client.post(
#             f"/api/routing/move/{active_visit.visit_id}",
#             json={"target_dept_id": str(target_dept.dept_id)},
#             headers=doctor_token_headers,
#         )

#         assert response.status_code == status.HTTP_200_OK

#         await db.refresh(active_visit)

#         assert active_visit.token_number == old_token


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 4: CURRENT LOCATION
# ══════════════════════════════════════════════════════════════════════════════


class TestCurrentLocation:
    """
    Test getting patient's current location in queue system.
    
    Endpoint: GET /api/routing/location/{visit_id}
    """

    async def test_get_current_location_success(
        self,
        client: AsyncClient,
        active_visit,
        queue_entry,
        receptionist_token_headers,
    ):
        """GET /api/routing/location/{visit_id} - Returns patient location."""

        # Act
        response = await client.get(
            f"/api/routing/location/{active_visit.visit_id}",
            headers=receptionist_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        assert data["visit_id"] == str(active_visit.visit_id)
        assert data["token_number"] == active_visit.token_number
        assert "current_department_name" in data
        assert "position_in_line" in data
        assert "estimated_wait_minutes" in data

    async def test_get_current_location_no_active_queue(
        self,
        client: AsyncClient,
        db,
        active_visit,
        queue_entry,
        receptionist_token_headers,
    ):
        """
        GET /api/routing/location/{visit_id}

        Visit exists but has no active queue entry.
        """
        # Arrange
        active_visit.current_queue_entry_id = None
        queue_entry.status = QueueEntryStatus.COMPLETED
        await db.commit()

        # Act
        response = await client.get(
            f"/api/routing/location/{active_visit.visit_id}",
            headers=receptionist_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        assert data["visit_id"] == str(active_visit.visit_id)
        assert data["token_number"] == active_visit.token_number
        assert data["visit_stage"] == VisitStage.ACTIVE.value

        assert data["current_queue_entry_id"] is None
        assert data["current_dept_id"] is None
        assert data["current_department_name"] is None
        assert data["status"] is None
        assert data["position_in_line"] == 0
        assert data["estimated_wait_minutes"] == 0
        assert data["assigned_staff_id"] is None
        assert data["entered_at"] is None

    async def test_get_current_location_visit_not_found(
        self,
        client: AsyncClient,
        receptionist_token_headers,
    ):
        """404 for unknown visit."""
        response = await client.get(
            f"/api/routing/location/{uuid4()}",
            headers=receptionist_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_current_location_invalid_uuid(
        self,
        client: AsyncClient,
        receptionist_token_headers,
    ):
        """422 for malformed UUID."""
        response = await client.get(
            "/api/routing/location/not-a-valid-uuid",
            headers=receptionist_token_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_get_current_location_unauthorized(
        self,
        client: AsyncClient,
        active_visit,
    ):
        """401 for missing authentication."""
        response = await client.get(
            f"/api/routing/location/{active_visit.visit_id}"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ══════════════════════════════════════════════════════════════════════════════
# GROUP 5: PATIENT HISTORY
# ══════════════════════════════════════════════════════════════════════════════


class TestPatientHistory:
    """
    Test getting patient's routing history.
    
    Endpoint: GET /api/routing/history/{visit_id}
    
    Requires: ADMIN or RECEPTIONIST role
    """

    async def test_get_patient_history_success(
        self,
        client: AsyncClient,
        db,
        active_visit,
        queue_entry,
        receptionist_token_headers,
    ):
        """
        GET /api/routing/history/{visit_id}

        Returns the patient's routing history.
        """
        # Act
        response = await client.get(
            f"/api/routing/history/{active_visit.visit_id}",
            headers=receptionist_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 1

        entry = data[0]

        assert entry["visit_id"] == str(active_visit.visit_id)
        assert entry["queue_entry_id"] == str(queue_entry.queue_entry_id)

    async def test_get_patient_history_ordered(
        self,
        client: AsyncClient,
        db,
        active_visit,
        receptionist_token_headers,
    ):
        """Queue history should be returned in chronological order."""
        # Act
        response = await client.get(
            f"/api/routing/history/{active_visit.visit_id}",
            headers=receptionist_token_headers,
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        entered_times = [entry["entered_at"] for entry in data]

        assert entered_times == sorted(entered_times)

    async def test_get_patient_history_visit_not_found(
        self,
        client: AsyncClient,
        receptionist_token_headers,
    ):
        """Unknown visit returns 404."""

        response = await client.get(
            f"/api/routing/history/{uuid4()}",
            headers=receptionist_token_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_patient_history_invalid_uuid(
        self,
        client: AsyncClient,
        receptionist_token_headers,
    ):
        """Invalid UUID returns validation error."""

        response = await client.get(
            "/api/routing/history/not-a-uuid",
            headers=receptionist_token_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_get_patient_history_unauthorized(
        self,
        client: AsyncClient,
        active_visit,
    ):
        """Missing JWT returns 401."""

        response = await client.get(
            f"/api/routing/history/{active_visit.visit_id}"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_patient_history_forbidden_role(
        self,
        client: AsyncClient,
        active_visit,
        doctor_token_headers,
    ):
        """Non-admin/receptionist cannot view history."""
        response = await client.get(
            f"/api/routing/history/{active_visit.visit_id}",
            headers=doctor_token_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_patient_history_response_schema(
        self,
        client: AsyncClient,
        active_visit,
        queue_entry,
        receptionist_token_headers,
    ):
        """Verify response includes expected fields."""
        response = await client.get(
            f"/api/routing/history/{active_visit.visit_id}",
            headers=receptionist_token_headers,
        )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        assert len(data) == 1

        entry = data[0]

        expected_fields = {
            "queue_entry_id",
            "visit_id",
            "dept_id",
            "status",
            "priority",
            "entered_at",
        }

        assert expected_fields.issubset(entry.keys())
