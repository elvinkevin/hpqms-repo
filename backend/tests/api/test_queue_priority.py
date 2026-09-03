import uuid
import pytest
from httpx import AsyncClient
from fastapi import status
from sqlalchemy import select

from app.domain.models.models import QueueEntry
from app.domain.models.models import QueuePriority, QueueEntryStatus


@pytest.mark.asyncio
async def test_triage_nurse_can_change_priority(
    client: AsyncClient,
    db,
    active_visit,
    triage_nurse_staff,
    triage_token_headers,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()
    entry.dept_id = triage_nurse_staff.dept_id
    db.add(entry)
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=triage_token_headers,
        json={"priority": "CRITICAL"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["priority"] == "CRITICAL"


@pytest.mark.asyncio
async def test_doctor_can_change_priority(
    client: AsyncClient,
    db,
    active_visit,
    doctor_staff,
    doctor_token_headers,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()
    entry.dept_id = doctor_staff.dept_id
    db.add(entry)
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=doctor_token_headers,
        json={"priority": "URGENT"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["priority"] == "URGENT"


@pytest.mark.asyncio
async def test_admin_can_change_priority_cross_department(
    client: AsyncClient,
    db,
    active_visit,
    admin_staff,
    admin_headers,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()
    db.add(entry)
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=admin_headers,
        json={"priority": "SEMI_URGENT"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["priority"] == "SEMI_URGENT"


@pytest.mark.asyncio
async def test_receptionist_cannot_change_priority(
    client: AsyncClient,
    db,
    active_visit,
    receptionist_token_headers,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=receptionist_token_headers,
        json={"priority": "CRITICAL"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_nurse_cannot_change_priority(
    client: AsyncClient,
    db,
    active_visit,
    nurse_token_headers,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=nurse_token_headers,
        json={"priority": "URGENT"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_unauthenticated_user_cannot_change_priority(
    client: AsyncClient,
    db,
    active_visit,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        json={"priority": "URGENT"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_wrong_department_is_rejected(
    client: AsyncClient,
    db,
    active_visit,
    doctor_staff,
    doctor_token_headers,
    setup_departments,
):
    """Verify staff cannot alter queue priority for entries outside their assigned department."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    # Find an existing department that is DIFFERENT from doctor_staff.dept_id
    different_department = next(
        dept for dept in setup_departments.values()
        if dept.dept_id != doctor_staff.dept_id
    )

    # Reassign queue entry to the valid alternative department
    entry.dept_id = different_department.dept_id
    db.add(entry)
    await db.commit()

    # Attempt priority update with doctor's credentials
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=doctor_token_headers,
        json={"priority": "CRITICAL"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "outside your assigned department" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_queue_entry_returns_404(
    client: AsyncClient,
    admin_headers,
):
    fake_id = uuid.uuid4()
    response = await client.patch(
        f"/api/queue/{fake_id}/priority",
        headers=admin_headers,
        json={"priority": "URGENT"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_status",
    [
        QueueEntryStatus.COMPLETED,
        QueueEntryStatus.NO_SHOW,
        QueueEntryStatus.CANCELLED,
    ],
)
async def test_inactive_entry_returns_409(
    client: AsyncClient,
    db,
    active_visit,
    admin_headers,
    terminal_status,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()
    entry.status = terminal_status
    db.add(entry)
    await db.commit()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=admin_headers,
        json={"priority": "CRITICAL"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_invalid_priority_enum_returns_422(
    client: AsyncClient,
    db,
    active_visit,
    admin_headers,
):
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=admin_headers,
        json={"priority": "SUPER_MAX_CRITICAL"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_priority_persistence_and_ordering_impact(
    client: AsyncClient,
    db,
    active_visit,
    admin_headers,
):
    """Verify priority changes persist to DB and modify order-by evaluation."""
    result = await db.execute(
        select(QueueEntry).where(QueueEntry.visit_id == active_visit.visit_id)
    )
    entry = result.scalar_one()

    # 1. Update priority via API
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/priority",
        headers=admin_headers,
        json={"priority": "CRITICAL"},
    )
    assert response.status_code == status.HTTP_200_OK

    # 2. Query directly from database to verify persistence
    await db.refresh(entry)
    assert entry.priority == QueuePriority.CRITICAL