import pytest
from uuid import uuid4
from fastapi import status
from httpx import AsyncClient

from app.domain.models.models import QueueEntryStatus, QueuePriority

pytestmark = pytest.mark.asyncio


# ── GROUP 1: RETRIEVAL & QUEUE LOOKUPS ───────────────────────────────────────

async def test_get_department_queue_success(
    client: AsyncClient, doctor_token_headers: dict, department, queue_entry
):
    """GET /api/queue/department/{department_id} - Returns list of QueueEntryRead"""
    response = await client.get(
        f"/api/queue/department/{department.dept_id}",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    # Schema assertions (QueueEntryRead)
    entry_data = data[0]
    assert entry_data["queue_entry_id"] == str(queue_entry.queue_entry_id)
    assert entry_data["department_id"] == str(department.dept_id)
    assert entry_data["priority"] == queue_entry.priority.value


async def test_get_department_queue_empty(
    client: AsyncClient, doctor_token_headers: dict
):
    """GET /api/queue/department/{department_id} - Handles non-existent department or empty queue"""
    empty_dept_id = uuid4()
    response = await client.get(
        f"/api/queue/department/{empty_dept_id}",
        headers=doctor_token_headers,
    )
    assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_200_OK)
    if response.status_code == status.HTTP_200_OK:
        assert response.json() == []


async def test_get_queue_entry_success(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """GET /api/queue/entry/{queue_entry_id} - Returns single QueueEntryRead"""
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


async def test_get_visit_queue_success(
    client: AsyncClient, doctor_token_headers: dict, active_visit, queue_entry
):
    """GET /api/queue/visit/{visit_id} - Returns active queue entry for visit"""
    response = await client.get(
        f"/api/queue/visit/{active_visit.visit_id}",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["visit_id"] == str(active_visit.visit_id)


async def test_get_next_patient_success(
    client: AsyncClient, doctor_token_headers: dict, department, queue_entry
):
    """GET /api/queue/department/{department_id}/next - Returns next waiting QueueEntryRead"""
    response = await client.get(
        f"/api/queue/department/{department.dept_id}/next",
        headers=doctor_token_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["queue_entry_id"] == str(queue_entry.queue_entry_id)


async def test_get_position_and_wait_time(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """GET /api/queue/{id}/position & wait-time - Returns position and wait time metrics"""
    pos_res = await client.get(
        f"/api/queue/{queue_entry.queue_entry_id}/position",
        headers=doctor_token_headers,
    )
    assert pos_res.status_code == status.HTTP_200_OK
    assert isinstance(pos_res.json(), int)

    wait_res = await client.get(
        f"/api/queue/{queue_entry.queue_entry_id}/wait-time",
        headers=doctor_token_headers,
    )
    assert wait_res.status_code == status.HTTP_200_OK
    assert isinstance(wait_res.json(), int)


# ── GROUP 2: STATE TRANSITIONS (HAPPY PATHS) ──────────────────────────────

async def test_queue_lifecycle_happy_path(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """PATCH transitions: WAITING -> CALLED -> IN_PROGRESS -> COMPLETED"""
    entry_id = queue_entry.queue_entry_id

    # 1. CALL
    res_call = await client.patch(
        f"/api/queue/{entry_id}/call",
        headers=doctor_token_headers,
    )
    assert res_call.status_code == status.HTTP_200_OK
    assert res_call.json()["status"] == QueueEntryStatus.CALLED.value

    # 2. START
    res_start = await client.patch(
        f"/api/queue/{entry_id}/start",
        headers=doctor_token_headers,
    )
    assert res_start.status_code == status.HTTP_200_OK
    assert res_start.json()["status"] == QueueEntryStatus.IN_PROGRESS.value

    # 3. COMPLETE
    res_comp = await client.patch(
        f"/api/queue/{entry_id}/complete",
        headers=doctor_token_headers,
    )
    assert res_comp.status_code == status.HTTP_200_OK
    assert res_comp.json()["status"] == QueueEntryStatus.COMPLETED.value


async def test_queue_no_show_path(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """PATCH transition: CALLED -> NO_SHOW"""
    entry_id = queue_entry.queue_entry_id

    # Call patient first
    await client.patch(
        f"/api/queue/{entry_id}/call",
        headers=doctor_token_headers,
    )

    # Mark as No-Show
    res_noshow = await client.patch(
        f"/api/queue/{entry_id}/no-show",
        headers=doctor_token_headers,
    )
    assert res_noshow.status_code == status.HTTP_200_OK
    assert res_noshow.json()["status"] == QueueEntryStatus.NO_SHOW.value


async def test_queue_cancel_path(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """PATCH transition: WAITING -> CANCELLED"""
    res_cancel = await client.patch(
        f"/api/queue/{queue_entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )
    assert res_cancel.status_code == status.HTTP_200_OK
    assert res_cancel.json()["status"] == QueueEntryStatus.CANCELLED.value


# ── GROUP 3: INVALID STATE TRANSITIONS ───────────────────────────────────────

async def test_invalid_transition_waiting_to_completed(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """Invalid transition: WAITING directly to COMPLETED"""
    response = await client.patch(
        f"/api/queue/{queue_entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY)


async def test_invalid_transition_cancelled_to_start(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """Invalid transition: CANCELLED entry cannot be started"""
    entry_id = queue_entry.queue_entry_id

    # Cancel entry
    await client.patch(
        f"/api/queue/{entry_id}/cancel",
        headers=doctor_token_headers,
    )

    # Attempt start on cancelled entry
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

from datetime import datetime

# ── GROUP 5: ADVANCED STATE TRANSITION EDGE CASES ───────────────────────────

async def test_complete_already_completed_queue_entry(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """
    Business Rule: Completing an already COMPLETED queue entry must fail.
    WAITING -> CALL -> START -> COMPLETE -> COMPLETE ❌
    """
    entry_id = queue_entry.queue_entry_id

    # Advance to COMPLETED
    await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    res_complete = await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)
    assert res_complete.status_code == status.HTTP_200_OK

    # Attempt second completion
    res_duplicate = await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)
    assert res_duplicate.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT, status.HTTP_422_UNPROCESSABLE_ENTITY)


async def test_call_already_completed_queue_entry(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """
    Business Rule: Calling a patient whose entry is already COMPLETED must fail.
    """
    entry_id = queue_entry.queue_entry_id

    # Advance to COMPLETED
    await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)

    # Attempt to re-call
    res_recall = await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    assert res_recall.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT, status.HTTP_422_UNPROCESSABLE_ENTITY)


async def test_cancel_already_completed_queue_entry(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """
    Business Rule: Cancelling an entry that is already COMPLETED must fail.
    """
    entry_id = queue_entry.queue_entry_id

    # Advance to COMPLETED
    await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)

    # Attempt cancel
    res_cancel = await client.patch(f"/api/queue/{entry_id}/cancel", headers=doctor_token_headers)
    assert res_cancel.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT, status.HTTP_422_UNPROCESSABLE_ENTITY)


# ── GROUP 6: TIMESTAMP METRIC VALIDATIONS ────────────────────────────────────

async def test_queue_transition_timestamps_populated(
    client: AsyncClient, doctor_token_headers: dict, queue_entry
):
    """
    Metric Rule: Verify that transitions populate called_at, started_at, and completed_at.
    """
    entry_id = queue_entry.queue_entry_id

    # 1. CALL -> expects called_at
    res_call = await client.patch(f"/api/queue/{entry_id}/call", headers=doctor_token_headers)
    data_call = res_call.json()
    assert data_call["called_at"] is not None
    assert isinstance(datetime.fromisoformat(data_call["called_at"].replace("Z", "+00:00")), datetime)

    # 2. START -> expects started_at
    res_start = await client.patch(f"/api/queue/{entry_id}/start", headers=doctor_token_headers)
    data_start = res_start.json()
    assert data_start["started_at"] is not None

    # 3. COMPLETE -> expects completed_at
    res_comp = await client.patch(f"/api/queue/{entry_id}/complete", headers=doctor_token_headers)
    data_comp = res_comp.json()
    assert data_comp["completed_at"] is not None


# ── GROUP 7: RBAC / AUTHORIZATION EDGE CASES ────────────────────────────────
async def test_call_patient_rbac_role_enforcement(
    client: AsyncClient, queue_entry
):
    """
    Authorization Rule: Requests with invalid tokens must be rejected.
    """
    entry_id = queue_entry.queue_entry_id

    # Attempt to call patient with invalid token
    invalid_headers = {"Authorization": "Bearer invalid.token.value"}
    response = await client.patch(
        f"/api/queue/{entry_id}/call",
        headers=invalid_headers,
    )
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)