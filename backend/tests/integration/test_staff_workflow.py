import pytest


@pytest.mark.asyncio
async def test_staff_can_view_department_queue(
    client,
    department,
    receptionist_staff,
    receptionist_token_headers,
    queue_entry,
):
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