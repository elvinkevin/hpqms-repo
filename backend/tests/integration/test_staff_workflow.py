import pytest
from app.domain.models.models import QueueEntry


@pytest.mark.asyncio
async def test_staff_can_view_department_queue(
    client,
    department,
    receptionist_staff,
    receptionist_token_headers,
    queue_entry,
    db,
):
    # Ensure queue entry and staff belong to the target department fixture
    queue_entry.dept_id = department.dept_id
    receptionist_staff.department_id = department.dept_id
    if hasattr(receptionist_staff, "dept_id"):
        receptionist_staff.dept_id = department.dept_id
        
    db.add(queue_entry)
    db.add(receptionist_staff)
    await db.commit()
    await db.refresh(queue_entry)
    await db.refresh(receptionist_staff)

    response = await client.get(
        f"/api/queue/department/{department.dept_id}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["queue_entry_id"] == str(
        queue_entry.queue_entry_id
    )

    assert data[0]["dept_id"] == str(
        department.dept_id
    )

    assert data[0]["status"] == "WAITING"