import pytest
from uuid import uuid4
from datetime import datetime
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession)
from app.domain.models.models import EntryType, QueueEntry, QueueEntryStatus, QueuePriority, Visit

pytestmark = pytest.mark.asyncio


# ── GROUP 1: RETRIEVAL & QUEUE LOOKUPS ───────────────────────────────────────

async def test_get_department_queue_success(
    client: AsyncClient, doctor_token_headers: dict, doctor_staff, department, queue_entry, db: AsyncSession
):
    # Align department IDs across staff, department, and queue entry
    doctor_staff.dept_id = department.dept_id
    queue_entry.dept_id = department.dept_id
    db.add_all([doctor_staff, queue_entry])
    await db.commit()

    response = await client.get(
        f"/api/queue/department/{department.dept_id}",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    entry_data = data[0]
    assert entry_data["queue_entry_id"] == str(queue_entry.queue_entry_id)
    assert entry_data["dept_id"] == str(department.dept_id)
    assert entry_data["priority"] == queue_entry.priority.value


async def test_get_department_queue_empty(
    client: AsyncClient, doctor_token_headers: dict
):
    """GET /api/queue/department/{dept_id} - Handles empty queue"""
    empty_dept_id = uuid4()
    response = await client.get(
        f"/api/queue/department/{empty_dept_id}",
        headers=doctor_token_headers,
    )
    # 403 when trying to access a department the staff doesn't belong to
    assert response.status_code in (
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_200_OK,
    )
    if response.status_code == status.HTTP_200_OK:
        assert response.json() == []


async def test_get_queue_entry_success(
    client: AsyncClient, doctor_token_headers: dict, doctor_staff, queue_entry, db: AsyncSession
):
    """GET /api/queue/entry/{queue_entry_id} - Returns single QueueEntryRead"""
    # Align the doctor's department with the queue entry's department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    response = await client.get(
        f"/api/queue/entry/{queue_entry.queue_entry_id}",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["queue_entry_id"] == str(queue_entry.queue_entry_id)
    assert data["visit_id"] == str(queue_entry.visit_id)


async def test_get_queue_entry_not_found(
    client: AsyncClient, doctor_token_headers: dict
):
    """GET /api/queue/entry/{queue_entry_id} - Returns 404 for unknown entry"""
    response = await client.get(
        f"/api/queue/entry/{uuid4()}",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_visit_queue_success(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    existing_patient,
    setup_departments,
    db: AsyncSession,
):
    target_dept_id = setup_departments["RECEPTION"].dept_id

    # Align staff department for RBAC
    doctor_staff.dept_id = target_dept_id
    db.add(doctor_staff)

    # 1. Create Visit with required patient_id
    visit = Visit(
        patient_id=existing_patient.patient_id,
        token_number="V-100",
        entry_type=EntryType.WALK_IN,
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
    await db.flush()  # Ensures visit_id is generated before linking QueueEntry

    # 2. Create QueueEntry with required visit_id and dept_id
    queue_entry = QueueEntry(
        visit_id=visit.visit_id,
        dept_id=target_dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add(queue_entry)
    await db.commit()

    # Call endpoint
    response = await client.get(
        f"/api/queue/visit/{visit.visit_id}",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK


async def test_get_next_patient_success(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    setup_departments,
    queue_entry,
    db: AsyncSession,
):
    """GET /api/queue/department/{dept_id}/next - Returns next waiting QueueEntryRead"""
    reception_dept_id = setup_departments["RECEPTION"].dept_id

    # Align staff and queue entry to RECEPTION
    doctor_staff.dept_id = reception_dept_id
    queue_entry.dept_id = reception_dept_id
    queue_entry.status = QueueEntryStatus.WAITING
    db.add_all([doctor_staff, queue_entry])
    await db.commit()

    response = await client.get(
        f"/api/queue/department/{reception_dept_id}/next",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["queue_entry_id"] == str(queue_entry.queue_entry_id)


@pytest.mark.asyncio
async def test_get_position_and_wait_time(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """GET /api/queue/{queue_entry_id}/position - Returns position & estimated wait time"""
    # 1. Align staff department with target queue entry for RBAC
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()
    await db.refresh(doctor_staff)

    # 2. Call endpoint using matching router path `/api/queue/{queue_entry_id}/position`
    response = await client.get(
        f"/api/queue/{queue_entry.queue_entry_id}/position",
        headers=doctor_token_headers,
    )
    
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), int)

# ── GROUP 2: STATE TRANSITIONS (HAPPY PATHS) ──────────────────────────────

async def test_queue_lifecycle_happy_path(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """Test full queue progression: call -> start -> complete"""
    # Align staff department to the queue entry's department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    # Call patient
    call_res = await client.patch(
        f"/api/queue/{queue_entry.queue_entry_id}/call",
        headers=doctor_token_headers,
    )
    assert call_res.status_code == status.HTTP_200_OK

    # Start patient interaction
    start_res = await client.patch(
        f"/api/queue/{queue_entry.queue_entry_id}/start",
        headers=doctor_token_headers,
    )
    assert start_res.status_code == status.HTTP_200_OK

    # Complete queue entry
    complete_res = await client.patch(
        f"/api/queue/{queue_entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )
    assert complete_res.status_code == status.HTTP_200_OK


async def test_queue_no_show_path(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """PATCH transition: CALLED -> NO_SHOW"""
    # Align staff department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    entry_id = queue_entry.queue_entry_id

    # Call patient first
    call_res = await client.patch(
        f"/api/queue/{entry_id}/call",
        headers=doctor_token_headers,
    )
    assert call_res.status_code == status.HTTP_200_OK

    # Mark as No-Show
    res_noshow = await client.patch(
        f"/api/queue/{entry_id}/no-show",
        headers=doctor_token_headers,
    )
    assert res_noshow.status_code == status.HTTP_200_OK
    assert res_noshow.json()["status"] == QueueEntryStatus.NO_SHOW.value


async def test_queue_cancel_path(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """PATCH transition: WAITING -> CANCELLED"""
    # Align staff department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    res_cancel = await client.patch(
        f"/api/queue/{queue_entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )
    assert res_cancel.status_code == status.HTTP_200_OK
    assert res_cancel.json()["status"] == QueueEntryStatus.CANCELLED.value


async def test_queue_requeue_path(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """
    PATCH transition: NO_SHOW -> WAITING (requeue)
    Tests the full lifecycle: WAITING -> CALLED -> NO_SHOW -> WAITING
    """
    # Align staff department with target queue entry
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    entry_id = queue_entry.queue_entry_id

    # 1. Call patient
    res_call = await client.patch(
        f"/api/queue/{entry_id}/call",
        headers=doctor_token_headers,
    )
    assert res_call.status_code == status.HTTP_200_OK

    # 2. Mark as no-show
    res_noshow = await client.patch(
        f"/api/queue/{entry_id}/no-show",
        headers=doctor_token_headers,
    )
    assert res_noshow.status_code == status.HTTP_200_OK
    assert res_noshow.json()["status"] == QueueEntryStatus.NO_SHOW.value

    # 3. Requeue (NO_SHOW -> WAITING)
    res_requeue = await client.patch(
        f"/api/queue/{entry_id}/requeue",
        headers=doctor_token_headers,
    )
    assert res_requeue.status_code == status.HTTP_200_OK
    data = res_requeue.json()
    assert data["status"] == QueueEntryStatus.WAITING.value
    assert data["assigned_staff_id"] is None


# ── GROUP 3: INVALID STATE TRANSITIONS ───────────────────────────────────────

async def test_invalid_transition_waiting_to_completed(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """Invalid transition: WAITING directly to COMPLETED should fail with 400/422"""
    # Align staff department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    response = await client.patch(
        f"/api/queue/{queue_entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY)


async def test_invalid_transition_cancelled_to_start(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """Invalid transition: CANCELLED entry cannot be started"""
    # Align staff department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    entry_id = queue_entry.queue_entry_id

    # 1. Cancel entry (authorized because departments match)
    res_cancel = await client.patch(
        f"/api/queue/{entry_id}/cancel",
        headers=doctor_token_headers,
    )
    assert res_cancel.status_code == status.HTTP_200_OK

    # 2. Attempt start on cancelled entry
    response = await client.patch(
        f"/api/queue/{entry_id}/start",
        headers=doctor_token_headers,
    )
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY)


# ── GROUP 4: SECURITY & AUTHORIZATION ───────────────────────────────────────

async def test_queue_unauthenticated(client: AsyncClient, queue_entry):
    """Unauthenticated call should return 401 Unauthorized"""
    response = await client.get(f"/api/queue/entry/{queue_entry.queue_entry_id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_queue_call_patient_rbac_role_enforcement(
    client: AsyncClient, queue_entry
):
    """Authorization Rule: Requests with invalid tokens must be rejected."""
    entry_id = queue_entry.queue_entry_id

    # Attempt to call patient with invalid token
    invalid_headers = {"Authorization": "Bearer invalid.token.value"}
    response = await client.patch(
        f"/api/queue/{entry_id}/call",
        headers=invalid_headers,
    )
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


# ── GROUP 5: ADVANCED STATE TRANSITION EDGE CASES ───────────────────────────

async def test_complete_already_completed_queue_entry(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """
    Business Rule: Completing an already COMPLETED queue entry must fail.
    WAITING -> CALL -> START -> COMPLETE -> COMPLETE ❌
    """
    # Align staff department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    entry_id = queue_entry.queue_entry_id

    # Advance to COMPLETED
    res_call = await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    assert res_call.status_code == status.HTTP_200_OK

    res_start = await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    assert res_start.status_code == status.HTTP_200_OK

    res_complete = await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)
    assert res_complete.status_code == status.HTTP_200_OK

    # Attempt second completion
    res_duplicate = await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)
    assert res_duplicate.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def test_call_already_completed_queue_entry(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """
    Business Rule: Calling a patient whose entry is already COMPLETED must fail.
    """
    # Align staff department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    entry_id = queue_entry.queue_entry_id

    # Advance to COMPLETED
    await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)

    # Attempt to re-call
    res_recall = await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    assert res_recall.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def test_cancel_already_completed_queue_entry(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """
    Business Rule: Cancelling an entry that is already COMPLETED must fail.
    """
    # Align staff department
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    entry_id = queue_entry.queue_entry_id

    # Advance to COMPLETED
    await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)

    # Attempt cancel
    res_cancel = await client.patch(f"/api/queue/{entry_id}/cancel", headers=doctor_token_headers)
    assert res_cancel.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
# ── GROUP 6: TIMESTAMP METRIC VALIDATIONS ────────────────────────────────────

async def test_queue_transition_timestamps_populated(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    queue_entry,
    db: AsyncSession,
):
    """
    Metric Rule: Verify that transitions populate called_at, started_at, and completed_at.
    """
    # Align staff department to pass authorization
    doctor_staff.dept_id = queue_entry.dept_id
    db.add(doctor_staff)
    await db.commit()

    entry_id = queue_entry.queue_entry_id

    # 1. CALL -> expects called_at
    res_call = await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    assert res_call.status_code == status.HTTP_200_OK
    data_call = res_call.json()

    # Support camelCase aliases if model is configured with by_alias=True
    called_at = data_call.get("called_at") or data_call.get("calledAt")
    assert called_at is not None
    assert isinstance(datetime.fromisoformat(called_at.replace("Z", "+00:00")), datetime)

    # 2. START -> expects started_at
    res_start = await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    assert res_start.status_code == status.HTTP_200_OK
    data_start = res_start.json()
    started_at = data_start.get("started_at") or data_start.get("startedAt")
    assert started_at is not None

    # 3. COMPLETE -> expects completed_at
    res_comp = await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)
    assert res_comp.status_code == status.HTTP_200_OK
    data_comp = res_comp.json()
    completed_at = data_comp.get("completed_at") or data_comp.get("completedAt")
    assert completed_at is not None


# @pytest.mark.asyncio
# async def test_queue_no_show_timestamps(
#     client: AsyncClient,
#     doctor_token_headers: dict,
#     doctor_staff,
#     queue_entry,
#     db: AsyncSession,
# ):
#     """
#     Metric Rule: NO_SHOW transitions should populate no_show_at timestamp,
#     and completed_at must remain None.
#     """
#     # 1. Align staff department with the queue entry to pass RBAC
#     doctor_staff.dept_id = queue_entry.dept_id
#     db.add(doctor_staff)
#     await db.commit()

#     entry_id = queue_entry.queue_entry_id

#     # 2. Call patient first (WAITING -> CALLED)
#     res_call = await client.patch(
#         f"/api/queue/{entry_id}/call",
#         headers=doctor_token_headers,
#     )
#     assert res_call.status_code == status.HTTP_200_OK

#     # 3. Mark as NO_SHOW (CALLED -> NO_SHOW)
#     res_noshow = await client.patch(
#         f"/api/queue/{entry_id}/no-show",
#         headers=doctor_token_headers,
#     )
#     assert res_noshow.status_code == status.HTTP_200_OK
#     data = res_noshow.json()

#     # Verify no_show_at is set and valid ISO timestamp
#     assert data.get("no_show_at") is not None
#     assert isinstance(
#         datetime.fromisoformat(data["no_show_at"].replace("Z", "+00:00")),
#         datetime,
#     )

#     # Verify completed_at is NOT populated for a no-show transition
#     assert data.get("completed_at") is None


# ── GROUP 7: DEPARTMENT ISOLATION ────────────────────────────────────────────

async def test_staff_cannot_operate_outside_department(
    client: AsyncClient, db, setup_departments, existing_patient, doctor_staff
):
    """
    Security Rule: A non-admin staff member cannot operate on queue entries
    from departments they're not assigned to.
    """
    from app.domain.models.models import QueueEntry, EntryType, Visit

    # Create visit in RECEPTION
    visit = Visit(
        patient_id=existing_patient.patient_id,
        token_number="TEST-001",
        entry_type=EntryType.WALK_IN,
        visit_reason="Test",
        stage=VisitStage.ACTIVE,
    )
    db.add(visit)
    await db.flush()

    # Create queue entry in RECEPTION (doctor is in TRIAGE or other dept)
    entry = QueueEntry(
        visit_id=visit.visit_id,
        dept_id=setup_departments["RECEPTION"].dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add(entry)
    await db.commit()

    # Attempt to call patient in wrong department
    headers = make_headers(doctor_staff)
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/call",
        headers=headers,
    )
    # Should either fail with 403 or not find the entry
    assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


# Helper function for the department isolation test
def make_headers(staff):
    from app.core.security import create_access_token
    token = create_access_token(
        {
            "sub": str(staff.staff_id),
            "employee_id": staff.employee_id,
            "role": staff.role.value if hasattr(staff.role, "value") else staff.role,
            "dept_id": str(staff.dept_id),
        }
    )
    return {"Authorization": f"Bearer {token}"}


# ── GROUP 8: CONCURRENT STAFF OPERATION GUARDS ───────────────────────────────

async def test_staff_cannot_call_multiple_patients(
    client: AsyncClient,
    doctor_token_headers: dict,
    doctor_staff,
    db: AsyncSession,
    setup_departments,
    existing_patient,
):
    """
    Business Rule: A staff member cannot call a second patient 
    while they already have one CALLED or IN_PROGRESS.
    """
    from app.domain.models.models import QueueEntry, Visit, VisitStage, EntryType, Patient

    reception_dept_id = setup_departments["RECEPTION"].dept_id

    # Align staff department with the target department
    doctor_staff.dept_id = reception_dept_id
    db.add(doctor_staff)

    # Create two patients
    patient2 = Patient(first_name="John", last_name="Doe2")
    db.add(patient2)
    await db.flush()

    # Create two visits in the same department
    visit1 = Visit(
        patient_id=existing_patient.patient_id,
        token_number="V-001",
        entry_type=EntryType.WALK_IN,
        stage=VisitStage.ACTIVE,
    )
    visit2 = Visit(
        patient_id=patient2.patient_id,
        token_number="V-002",
        entry_type=EntryType.WALK_IN,
        stage=VisitStage.ACTIVE,
    )
    db.add_all([visit1, visit2])
    await db.flush()

    # Create queue entries for both
    entry1 = QueueEntry(
        visit_id=visit1.visit_id,
        dept_id=reception_dept_id,
        sequence_number=1,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    entry2 = QueueEntry(
        visit_id=visit2.visit_id,
        dept_id=reception_dept_id,
        sequence_number=2,
        priority=QueuePriority.NORMAL,
        status=QueueEntryStatus.WAITING,
    )
    db.add_all([entry1, entry2])
    await db.commit()

    # Call first patient
    res1 = await client.patch(
        f"/api/queue/{entry1.queue_entry_id}/call",
        headers=doctor_token_headers,
    )
    assert res1.status_code == status.HTTP_200_OK

    # Attempt to call second patient
    res2 = await client.patch(
        f"/api/queue/{entry2.queue_entry_id}/call",
        headers=doctor_token_headers,
    )
    # Should fail with conflict
    assert res2.status_code in (status.HTTP_409_CONFLICT, status.HTTP_400_BAD_REQUEST)


# Import Patient for test
from app.domain.models.models import Patient, VisitStage