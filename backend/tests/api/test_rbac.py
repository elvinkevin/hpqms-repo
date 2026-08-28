from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.models.models import Staff, StaffRole
from app.domain.models.models import QueueEntry, QueueEntryStatus, VisitStage

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
            "target_department_id": str(target_department.dept_id),
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
            "target_department_id": str(target_department.dept_id),
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
            "target_department_id": str(target_department.dept_id),
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
            "target_department_id": str(target_department.dept_id),
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
            "target_department_id": str(target_department.dept_id),
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
            "target_department_id": str(target_department.dept_id),
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
    current_entry.department_id = doctor_staff.dept_id
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
    current_entry.department_id = triage_nurse_staff.dept_id
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
    current_entry.department_id = receptionist_staff.dept_id
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
    current_entry.department_id = nurse_staff.dept_id
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
    current_entry.department_id = triage_dept.dept_id
    await db.commit()

    response = await client.patch(
        f"/api/queue/{current_entry.queue_entry_id}/call",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
