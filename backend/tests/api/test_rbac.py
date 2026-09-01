from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.models import Department, Staff, StaffRole, Visit
from app.domain.models.models import QueueEntry, QueueEntryStatus, VisitStage
from datetime import datetime, timezone
pytestmark = pytest.mark.asyncio

@pytest.fixture
async def doctor(db, department):
    # Check if DOC001 already exists in the test database
    result = await db.execute(
        select(Staff).where(Staff.employee_id == "DOC001")
    )
    staff = result.scalar_one_or_none()

    if staff is None:
        staff = Staff(
            employee_id="DOC001",
            first_name="Doctor",
            last_name="User",
            role=StaffRole.DOCTOR,
            dept_id=department.dept_id,
            hashed_password="ignored",
            is_active=True,
        )
        db.add(staff)
        await db.commit()
        await db.refresh(staff)

    return staff



@pytest.mark.asyncio
async def test_doctor_can_discharge_patient(
    client: AsyncClient,
    db,
    active_visit,
    doctor_staff,
    doctor_token_headers,
):
    """
    A doctor can successfully discharge an active patient.
    """
    from sqlalchemy import select
    from app.domain.models.models import QueueEntry, QueueEntryStatus

    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = doctor_staff.staff_id
    current_entry.dept_id = doctor_staff.dept_id  # <--- Align department
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
    """
    A receptionist is forbidden from discharging a patient.
    """
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_triage_nurse_cannot_discharge_patient(
    client: AsyncClient,
    active_visit,
    triage_headers,
):
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge",
        headers=triage_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_triage_nurse_cannot_discharge_patient(
    client: AsyncClient,
    active_visit,
    triage_token_headers,
):
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
    """
    An admin can successfully discharge an active patient.
    """
    from sqlalchemy import select
    from app.domain.models.models import QueueEntry, QueueEntryStatus

    # Retrieve existing QueueEntry, transition to IN_PROGRESS, and assign staff
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/discharge"
    )

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
    """
    A doctor can transfer an in-progress patient to another department.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = doctor_staff.staff_id
    current_entry.dept_id = doctor_staff.dept_id  # <--- Align department
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
    """
    A triage nurse can route/transfer an in-progress patient to consultation.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = triage_nurse_staff.staff_id
    current_entry.dept_id = triage_nurse_staff.dept_id  # <--- Align department
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

async def test_admin_can_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    admin_staff,
    admin_headers,
    setup_departments,
):
    """
    An admin can perform transfers across departments.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS

    # Ensure assigned staff matches the user behind admin_headers
    current_entry.assigned_staff_id = admin_staff.staff_id
    await db.commit()

    target_department = setup_departments["CONSULT"]

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


async def test_receptionist_cannot_transfer_patient(
    client: AsyncClient,
    db,
    active_visit,
    receptionist_token_headers,
    setup_departments,
):
    """
    A receptionist cannot transfer an active patient.
    """
    # Transition to IN_PROGRESS so domain check passes and role check triggers
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    """
    A standard ward nurse cannot perform routing/transfers.
    """
    # Transition to IN_PROGRESS so domain check passes and role check triggers
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    """
    Unauthenticated users are denied access to patient transfers.
    """
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
# BATCH 1: CALL PATIENT (PATCH /api/queue/{id}/call)
# Expected transition: WAITING -> CALLED
# ============================================================================


@pytest.mark.asyncio
async def test_doctor_can_call(
    client: AsyncClient,
    db,
    active_visit,
    doctor_token_headers,
    doctor_staff,
    setup_departments,
):
    """
    A Doctor can call a WAITING patient in their assigned department.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    setup_departments,
):
    """
    A Triage Nurse can call a WAITING patient in the triage department.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    setup_departments,
):
    """
    A Receptionist can call a WAITING patient in the reception department.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    setup_departments,
):
    """
    A Ward Nurse can call a WAITING patient in their assigned department.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    setup_departments,
):
    """
    An Admin can perform a call operation across system queue entries.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    """
    Unauthenticated callers are rejected with 401 Unauthorized.
    """
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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
    """
    Cross-Department Guard Test: A Doctor in Consultation cannot call
    a patient currently queued in another department.
    """
    triage_dept = setup_departments["TRIAGE"]

    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
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


@pytest.mark.asyncio
async def test_unauthenticated_cannot_start_queue_entry(
    async_client: AsyncClient,
    called_queue_entry: QueueEntry,
):
    """Verify unauthenticated users cannot start a queue entry."""
    response = await async_client.post(
        f"/api/v1/queue/{called_queue_entry.queue_entry_id}/start",
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_cannot_start_queue_entry(
    client: AsyncClient,
    db: AsyncSession,
    active_visit: Visit,
):
    """Verify unauthenticated users cannot start a queue entry."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()

    # Use PUT (or PATCH depending on your route definition)
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_start_called_queue_entry_success(
    client: AsyncClient,
    db: AsyncSession,
    doctor_token_headers: dict,
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Verify that assigned staff can start a CALLED queue entry."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()

    # Move entry to CALLED and assign to doctor
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
    """Verify staff cannot start an entry called by another staff member."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()
    entry.status = QueueEntryStatus.CALLED
    entry.assigned_staff_id = receptionist_staff.staff_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
        headers=doctor_token_headers,
    )

    assert response.status_code == 403


# @pytest.mark.asyncio
# async def test_cannot_start_cross_department_entry(
#     client: AsyncClient,
#     db: AsyncSession,
#     doctor_token_headers: dict,
#     doctor_staff: Staff,
#     active_visit: Visit,
# ):
#     """Verify staff cannot start an entry belonging to a different department."""
#     # 1. Create a second valid department in the database
#     other_dept = Department(
#         name="Other Department",
#         code="OTHER_DEPT",
#         is_active=True,
#     )
#     db.add(other_dept)
#     await db.commit()
#     await db.refresh(other_dept)

#     # 2. Assign the queue entry to the second department
#     result = await db.execute(
#         select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
#     )
#     entry = result.scalars().first()
#     entry.status = QueueEntryStatus.CALLED
#     entry.assigned_staff_id = doctor_staff.staff_id
#     entry.dept_id = other_dept.dept_id  # References a real department in DB
#     await db.commit()

#     # 3. Request with doctor credentials from a different department
#     response = await client.patch(
#         f"/api/queue/{entry.queue_entry_id}/start",
#         headers=doctor_token_headers,
#     )

#     assert response.status_code == 403


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
    entry = result.scalars().first()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.IN_PROGRESS
    entry.started_at = datetime.now(timezone.utc)

    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
        headers=doctor_token_headers,
        json={},  # Include empty JSON payload in case schema requires a body
    )

    # Accepts either 400 or 422 depending on validation layer response
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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

    # Set staff and department so authorization passes
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
    entry = result.scalars().first()

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
    # Create a secondary valid department to avoid FK violation errors
    other_dept = Department(name="Other Dept", department_code="OTHER_DEPT", is_active=True)
    db.add(other_dept)
    await db.commit()
    await db.refresh(other_dept)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = other_dept.dept_id  # Cross-department mismatch
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
    entry = result.scalars().first()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/no-show",
    )

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    doctor_staff: Staff,
    active_visit: Visit,
):
    """Staff cannot requeue an entry belonging to another department."""
    # 1. Create a secondary department row
    other_dept = Department(name="Other Dept", department_code="OTHER_DEPT", is_active=True)
    db.add(other_dept)
    await db.commit()
    await db.refresh(other_dept)

    # 2. Fetch the queue entry
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()

    # 3. Assign entry to other_dept without linking doctor_staff
    entry.assigned_staff_id = None  # Unassigned, or assigned to staff in other_dept
    entry.dept_id = other_dept.dept_id
    entry.status = QueueEntryStatus.NO_SHOW
    await db.commit()

    # 4. Requesting doctor attempts to operate on cross-department entry
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
    entry = result.scalars().first()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
    )

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
    entry = result.scalars().first()

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
    """If your service permits cancelling WAITING entries, assert status code 200."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()

    entry.assigned_staff_id = doctor_staff.staff_id
    entry.dept_id = doctor_staff.dept_id
    entry.status = QueueEntryStatus.WAITING
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
        headers=doctor_token_headers,
    )

    # Adjust status check based on business logic (e.g., 200 if allowed, or keep 400 if strictly blocked)
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
    """If your service permits cancelling CALLED entries, assert status code 200."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    # Supply dummy hashed_password to satisfy non-null DB constraint
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
    entry = result.scalars().first()

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
    # Create secondary department row in DB
    other_dept = Department(name="Other Dept", department_code="OTHER_DEPT", is_active=True)
    db.add(other_dept)
    await db.commit()
    await db.refresh(other_dept)

    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalars().first()

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
    entry = result.scalars().first()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/cancel",
    )

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

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
    entry = result.scalars().first()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
    )

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
    entry = result.scalars().first()

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
    # Verify the visit stage remains active or unchanged
    assert active_visit.completed_at is None