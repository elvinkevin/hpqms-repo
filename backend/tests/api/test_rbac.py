from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import (
    Department,
    QueueEntry,
    QueueEntryStatus,
    Staff,
    Visit,
)

pytestmark = pytest.mark.asyncio


# ============================================================================
# DISCHARGE RBAC TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_doctor_can_discharge_patient(
    client: AsyncClient,
    db,
    active_visit,
    doctor_staff,
    doctor_token_headers,
):
    """A doctor can successfully discharge an active patient."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = doctor_staff.staff_id
    current_entry.dept_id = doctor_staff.dept_id
    await db.commit()

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK


async def test_receptionist_cannot_discharge_patient(
    client: AsyncClient,
    active_visit,
    receptionist_token_headers,
):
    """A receptionist is forbidden from discharging a patient."""
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_triage_nurse_cannot_discharge_patient(
    client: AsyncClient,
    active_visit,
    triage_token_headers,
):
    """A triage nurse is forbidden from discharging a patient."""
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge",
        headers=triage_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_nurse_cannot_discharge_patient(
    client: AsyncClient,
    active_visit,
    nurse_token_headers,
):
    """A ward nurse is forbidden from discharging a patient."""
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge",
        headers=nurse_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_admin_can_discharge_patient(
    client: AsyncClient,
    db,
    active_visit,
    admin_staff,
    admin_headers,
):
    """An admin can successfully discharge an active patient."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = admin_staff.staff_id
    await db.commit()

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK


async def test_unauthenticated_cannot_discharge_patient(
    client: AsyncClient,
    active_visit,
):
    """Unauthenticated callers cannot discharge a patient."""
    response = await client.post(f"/api/routing/{active_visit.visit_id}/discharge")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TRANSFER RBAC TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_doctor_can_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    doctor_staff,
    doctor_token_headers,
    setup_departments,
):
    """A doctor can transfer an in-progress patient to another department."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = doctor_staff.staff_id
    current_entry.dept_id = doctor_staff.dept_id
    await db.commit()

    target_department = setup_departments["TRIAGE"]

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        headers=doctor_token_headers,
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Transferred for further assessment.",
        },
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_triage_nurse_can_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    triage_nurse_staff,
    triage_token_headers,
    setup_departments,
):
    """A triage nurse can route/transfer an in-progress patient to consultation."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = triage_nurse_staff.staff_id
    current_entry.dept_id = triage_nurse_staff.dept_id
    await db.commit()

    target_department = setup_departments["CONSULT"]

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        headers=triage_token_headers,
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Triage complete. Forwarding to doctor.",
        },
    )

    assert response.status_code == status.HTTP_200_OK

@pytest.mark.asyncio
async def test_admin_can_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    admin_staff,
    admin_headers,
    setup_departments,
):
    """An admin can perform transfers across departments."""
    # 1. Ensure admin_staff exists and is flushed to the DB
    db.add(admin_staff)
    await db.commit()
    await db.refresh(admin_staff)

    # 2. Update the active queue entry to IN_PROGRESS and assign to admin
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = admin_staff.staff_id
    db.add(current_entry)
    await db.commit()

    # 3. Retrieve target department
    target_department = setup_departments.get("CONSULT") or setup_departments.get("consult")

    # 4. Execute transfer API call
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        headers=admin_headers,
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Admin override transfer.",
        },
    )

    assert response.status_code == status.HTTP_200_OK

    # 5. Verify the response contains the new queue entry details
    data = response.json()
    assert data["dept_id"] == str(target_department.dept_id)
    assert data["status"] == QueueEntryStatus.WAITING.value



async def test_receptionist_cannot_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    receptionist_token_headers,
    setup_departments,
):
    """A receptionist cannot transfer an active patient."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    target_department = setup_departments["CONSULT"]

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        headers=receptionist_token_headers,
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Unauthorized receptionist transfer.",
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_nurse_cannot_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    nurse_token_headers,
    setup_departments,
):
    """A standard ward nurse cannot perform routing/transfers."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    target_department = setup_departments["CONSULT"]

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        headers=nurse_token_headers,
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Unauthorized nurse transfer.",
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_unauthenticated_cannot_transfer_patient(
    client: AsyncClient,
    active_visit,
    setup_departments,
):
    """Unauthenticated users are denied access to patient transfers."""
    target_department = setup_departments["CONSULT"]

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Unauthenticated transfer attempt.",
        },
    )

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


# ============================================================================
# CALL PATIENT (PATCH /api/queue/{id}/call) — WAITING -> CALLED
# ============================================================================


@pytest.mark.asyncio
async def test_doctor_can_call(
    client: AsyncClient,
    db,
    active_visit,
    doctor_token_headers,
    doctor_staff,
):
    """A doctor can call a WAITING patient in their assigned department."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.WAITING
    current_entry.dept_id = doctor_staff.dept_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{current_entry.queue_entry_id}/call",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(current_entry)
    assert current_entry.status == QueueEntryStatus.CALLED


@pytest.mark.asyncio
async def test_triage_nurse_can_call(
    client: AsyncClient,
    db,
    active_visit,
    triage_token_headers,
    triage_nurse_staff,
):
    """A triage nurse can call a WAITING patient in the triage department."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.WAITING
    current_entry.dept_id = triage_nurse_staff.dept_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{current_entry.queue_entry_id}/call",
        headers=triage_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(current_entry)
    assert current_entry.status == QueueEntryStatus.CALLED


@pytest.mark.asyncio
async def test_receptionist_can_call(
    client: AsyncClient,
    db,
    active_visit,
    receptionist_token_headers,
    receptionist_staff,
):
    """A receptionist can call a WAITING patient in the reception department."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.WAITING
    current_entry.dept_id = receptionist_staff.dept_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{current_entry.queue_entry_id}/call",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(current_entry)
    assert current_entry.status == QueueEntryStatus.CALLED


@pytest.mark.asyncio
async def test_nurse_can_call(
    client: AsyncClient,
    db,
    active_visit,
    nurse_token_headers,
    nurse_staff,
):
    """A ward nurse can call a WAITING patient in their assigned department."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.WAITING
    current_entry.dept_id = nurse_staff.dept_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{current_entry.queue_entry_id}/call",
        headers=nurse_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(current_entry)
    assert current_entry.status == QueueEntryStatus.CALLED


@pytest.mark.asyncio
async def test_admin_can_call(
    client: AsyncClient,
    db,
    active_visit,
    admin_headers,
):
    """An admin can perform a call operation across system queue entries."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.WAITING
    await db.commit()

    response = await client.patch(
        f"/api/queue/{current_entry.queue_entry_id}/call",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(current_entry)
    assert current_entry.status == QueueEntryStatus.CALLED


@pytest.mark.asyncio
async def test_unauthenticated_cannot_call(
    client: AsyncClient,
    db,
    active_visit,
):
    """Unauthenticated callers are rejected with 401."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.WAITING
    await db.commit()

    response = await client.patch(f"/api/queue/{current_entry.queue_entry_id}/call")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_doctor_cannot_call_cross_department_entry(
    client: AsyncClient,
    db,
    active_visit,
    doctor_token_headers,
    setup_departments,
):
    """A doctor cannot call a patient currently queued in another department."""
    triage_dept = setup_departments["TRIAGE"]

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.WAITING
    current_entry.dept_id = triage_dept.dept_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{current_entry.queue_entry_id}/call",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# START (PATCH /api/queue/{id}/start) — CALLED -> IN_PROGRESS
# ============================================================================


@pytest.mark.asyncio
async def test_unauthenticated_cannot_start_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    active_visit: Visit,
):
    """Unauthenticated users cannot start a queue entry."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(f"/api/queue/{entry.queue_entry_id}/start")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_start_called_queue_entry_success(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Assigned staff can start a CALLED queue entry."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.status = QueueEntryStatus.CALLED
    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
        headers=doctor_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == QueueEntryStatus.IN_PROGRESS.value
    assert data["started_at"] is not None

    await db.refresh(entry)
    assert entry.status == QueueEntryStatus.IN_PROGRESS
    assert entry.started_at is not None


@pytest.mark.asyncio
async def test_cannot_start_entry_assigned_to_another_staff(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    receptionist_staff: Staff,
    active_visit: Visit,
):
    """Staff cannot start an entry called by another staff member."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()
    entry.status = QueueEntryStatus.CALLED
    entry.assigned_staff_id = receptionist_staff.staff_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_start_already_in_progress_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """An already IN_PROGRESS entry cannot be started again."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    entry.started_at = datetime.now(timezone.utc)

    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
        headers=doctor_token_headers,
        json={},
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_start_nonexistent_queue_entry_returns_404(
    client: AsyncClient,
    doctor_token_headers: dict,
):
    """Starting a queue entry that does not exist should return 404."""
    response = await client.patch(
        f"/api/queue/{uuid4()}/start",
        headers=doctor_token_headers,
    )

    assert response.status_code == 404


# ============================================================================
# NO-SHOW (PATCH /api/queue/{id}/no-show) — CALLED -> NO_SHOW
# ============================================================================


@pytest.mark.asyncio
async def test_assigned_staff_can_mark_no_show(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Assigned staff can mark a CALLED patient as NO_SHOW."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.CALLED
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/no-show",
        headers=doctor_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == QueueEntryStatus.NO_SHOW.value

    await db.refresh(entry)
    assert entry.status == QueueEntryStatus.NO_SHOW


@pytest.mark.asyncio
async def test_cannot_mark_waiting_patient_no_show(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A WAITING patient must be CALLED before being marked NO_SHOW."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.WAITING
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/no-show",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_mark_in_progress_patient_no_show(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """An IN_PROGRESS encounter cannot be marked NO_SHOW."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    entry.started_at = datetime.now(timezone.utc)
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/no-show",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_mark_cross_department_entry_no_show(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Staff cannot operate on a queue entry in another department."""
    other_dept = Department(name="Other Dept", department_code="OTHER_DEPT", is_active=True)
    db.add(other_dept)
    await db.commit()
    await db.refresh(other_dept)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = other_dept.dept_id
    entry.status = QueueEntryStatus.CALLED
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/no-show",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_mark_no_show(
    client: AsyncClient,
    db: AsyncSession,
    active_visit: Visit,
):
    """Unauthenticated users cannot mark queue entries as NO_SHOW."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(f"/api/queue/{entry.queue_entry_id}/no-show")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mark_no_show_nonexistent_entry_returns_404(
    client: AsyncClient,
    doctor_token_headers: dict,
):
    """A nonexistent queue entry cannot be marked NO_SHOW."""
    response = await client.patch(
        f"/api/queue/{uuid4()}/no-show",
        headers=doctor_token_headers,
    )

    assert response.status_code == 404


# ============================================================================
# REQUEUE (PATCH /api/queue/{id}/requeue) — NO_SHOW -> WAITING
# ============================================================================


@pytest.mark.asyncio
async def test_requeue_no_show_entry_success(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A staff member can requeue a NO_SHOW entry back to WAITING."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.NO_SHOW
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
        headers=doctor_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == QueueEntryStatus.WAITING.value

    await db.refresh(entry)
    assert entry.status == QueueEntryStatus.WAITING


@pytest.mark.asyncio
async def test_cannot_requeue_waiting_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A WAITING entry cannot be requeued."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.WAITING
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_requeue_called_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A CALLED entry cannot be requeued directly."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.CALLED
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_requeue_in_progress_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """An IN_PROGRESS entry cannot be requeued."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_requeue_cross_department_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    active_visit: Visit,
):
    """Staff cannot requeue an entry belonging to another department."""
    other_dept = Department(name="Other Dept", department_code="OTHER_DEPT", is_active=True)
    db.add(other_dept)
    await db.commit()
    await db.refresh(other_dept)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = None
    entry.dept_id = other_dept.dept_id
    entry.status = QueueEntryStatus.NO_SHOW
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_requeue(
    client: AsyncClient,
    db: AsyncSession,
    active_visit: Visit,
):
    """Unauthenticated users cannot requeue patients."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(f"/api/queue/{entry.queue_entry_id}/requeue")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_requeue_unknown_queue_entry(
    client: AsyncClient,
    doctor_token_headers: dict,
):
    """Unknown queue entry IDs return 404."""
    response = await client.patch(
        f"/api/queue/{uuid4()}/requeue",
        headers=doctor_token_headers,
    )

    assert response.status_code == 404


# ============================================================================
# CANCEL (PATCH /api/queue/{id}/cancel)
# ============================================================================


@pytest.mark.asyncio
async def test_cancel_in_progress_queue_entry_success(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Assigned staff can cancel an IN_PROGRESS queue entry."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    payload = {"notes": "Patient requested cancellation."}

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == QueueEntryStatus.CANCELLED.value

    await db.refresh(entry)
    assert entry.status == QueueEntryStatus.CANCELLED


@pytest.mark.asyncio
async def test_can_cancel_waiting_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """WAITING entries can be cancelled per current business rules."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.WAITING
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == QueueEntryStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_can_cancel_called_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """CALLED entries can be cancelled per current business rules."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.CALLED
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == QueueEntryStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cannot_cancel_completed_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A COMPLETED queue entry cannot be cancelled."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.COMPLETED
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_cancel_no_show_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A NO_SHOW queue entry cannot be cancelled."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.NO_SHOW
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_cancel_entry_assigned_to_another_staff(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Staff cannot cancel another staff member's active encounter."""
    other_staff = Staff(
        staff_id=uuid4(),
        dept_id=doctor_staff.dept_id,
        employee_id="DOC-9998",
        first_name="Jane",
        last_name="Doe",
        role=doctor_staff.role,
        hashed_password="hashed_secret_placeholder",
        is_active=True,
    )
    db.add(other_staff)
    await db.commit()
    await db.refresh(other_staff)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = other_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_cancel_cross_department_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    active_visit: Visit,
):
    """Staff cannot cancel an entry belonging to another department."""
    other_dept = Department(name="Other Dept", department_code="OTHER_DEPT", is_active=True)
    db.add(other_dept)
    await db.commit()
    await db.refresh(other_dept)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = None
    entry.dept_id = other_dept.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_cancel(
    client: AsyncClient,
    db: AsyncSession,
    active_visit: Visit,
):
    """Unauthenticated users cannot cancel entries."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(f"/api/queue/{entry.queue_entry_id}/cancel")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cancel_unknown_queue_entry(
    client: AsyncClient,
    doctor_token_headers: dict,
):
    """Unknown queue entry IDs return 404."""
    response = await client.patch(
        f"/api/queue/{uuid4()}/cancel",
        headers=doctor_token_headers,
    )

    assert response.status_code == 404


# ============================================================================
# COMPLETE (PATCH /api/queue/{id}/complete)
# ============================================================================


@pytest.mark.asyncio
async def test_complete_in_progress_queue_entry_success(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Assigned staff can complete an IN_PROGRESS queue entry."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
        json={"notes": "Encounter completed successfully."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == QueueEntryStatus.COMPLETED.value
    assert data.get("completed_at") is not None

    await db.refresh(entry)
    assert entry.status == QueueEntryStatus.COMPLETED
    assert entry.completed_at is not None


@pytest.mark.asyncio
async def test_cannot_complete_waiting_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A WAITING entry cannot be completed directly."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.WAITING
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_complete_called_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A CALLED entry must be started before completion."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.CALLED
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_complete_completed_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A COMPLETED queue entry cannot be completed twice."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.COMPLETED
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_complete_no_show_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """A NO_SHOW entry cannot be completed."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.NO_SHOW
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code in (400, 422)
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_cannot_complete_entry_assigned_to_another_staff(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Staff cannot complete another staff member's encounter."""
    other_staff = Staff(
        staff_id=uuid4(),
        dept_id=doctor_staff.dept_id,
        employee_id="DOC-9997",
        first_name="Alice",
        last_name="Smith",
        role=doctor_staff.role,
        hashed_password="hashed_secret_placeholder",
        is_active=True,
    )
    db.add(other_staff)
    await db.commit()
    await db.refresh(other_staff)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = other_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_complete_cross_department_entry(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    active_visit: Visit,
):
    """Staff cannot complete an entry belonging to another department."""
    other_dept = Department(name="Other Dept", department_code="OTHER_DEPT", is_active=True)
    db.add(other_dept)
    await db.commit()
    await db.refresh(other_dept)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = None
    entry.dept_id = other_dept.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_complete_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    active_visit: Visit,
):
    """Unauthenticated users cannot complete queue entries."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(f"/api/queue/{entry.queue_entry_id}/complete")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_complete_unknown_queue_entry_returns_404(
    client: AsyncClient,
    doctor_token_headers: dict,
):
    """Unknown queue entry IDs return 404."""
    response = await client.patch(
        f"/api/queue/{uuid4()}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_completing_queue_entry_does_not_complete_visit(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Completing a department queue step must NOT complete the hospital visit.

    QueueEntryStatus.COMPLETED != Visit lifecycle stage completion.
    """
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=doctor_token_headers,
    )

    assert response.status_code == 200

    await db.refresh(entry)
    await db.refresh(active_visit)

    assert entry.status == QueueEntryStatus.COMPLETED
    assert active_visit.completed_at is None


@pytest.mark.asyncio
async def test_triage_nurse_can_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    triage_nurse_staff,
    triage_token_headers,
    setup_departments,
):
    """A triage nurse can perform transfers across departments."""
    # Ensure triage nurse staff is committed and visible to the session
    db.add(triage_nurse_staff)
    await db.commit()

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = triage_nurse_staff.staff_id
    db.add(current_entry)
    await db.commit()

    target_department = setup_departments.get("CONSULT") or setup_departments.get("consult")

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        headers=triage_token_headers,
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Triage nurse authorized transfer.",
        },
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["dept_id"] == str(target_department.dept_id)
    assert data["status"] == QueueEntryStatus.WAITING.value


@pytest.mark.asyncio
async def test_admin_can_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    admin_staff,
    admin_headers,
    setup_departments,
):
    """An admin can perform transfers across departments."""
    # Ensure admin staff is committed and visible to the session
    db.add(admin_staff)
    await db.commit()

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = admin_staff.staff_id
    db.add(current_entry)
    await db.commit()

    target_department = setup_departments.get("CONSULT") or setup_departments.get("consult")

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        headers=admin_headers,
        json={
            "target_dept_id": str(target_department.dept_id),
            "reason": "DEPARTMENT_TRANSFER",
            "priority": "NORMAL",
            "notes": "Admin override transfer.",
        },
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["dept_id"] == str(target_department.dept_id)
    assert data["status"] == QueueEntryStatus.WAITING.value