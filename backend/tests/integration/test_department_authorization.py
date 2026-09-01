from fastapi import HTTPException
import pytest
from uuid import uuid4

from app.domain.models.models import (
    Department,
    DeptType,
    EntryType,
    QueueEntry,
    QueueEntryStatus,
    Staff,
    StaffRole,
)
from app.domain.schemas.schemas import VisitCreate
from app.core.security import create_access_token, hash_password
from tests.conftest import queue_entry


@pytest.mark.asyncio
async def test_staff_can_access_own_department(
    client,
    db,
    receptionist_staff,            # FIX: Changed from receptionist
    receptionist_token_headers,    # FIX: Injected available token headers fixture
    setup_departments,
):
    # Depending on how setup_departments is keyed (check if string is lower or uppercase)
    reception = setup_departments.get("reception") or setup_departments.get("RECEPTION")

    response = await client.get(
        f"/api/queue/department/{reception.dept_id}",
        headers=receptionist_token_headers,  # FIX: Passes {"Authorization": "Bearer ..."} directly
    )

    assert response.status_code == 200

@pytest.mark.asyncio
async def test_staff_cannot_access_other_department(
    client,
    receptionist_token_headers,    # FIX: Changed from receptionist
    setup_departments,
):
    # Adjust dictionary lookup casing based on how setup_departments populates it
    triage = setup_departments.get("triage") or setup_departments.get("TRIAGE")

    response = await client.get(
        f"/api/queue/department/{triage.dept_id}",
        headers=receptionist_token_headers,  # FIX: Passes authorization block directly
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You are not authorized to access this department."
    )

@pytest.mark.asyncio
async def test_staff_can_call_entry_in_own_department(
    client,
    receptionist_token_headers,    # FIX: Changed from receptionist
    reception_queue_entry,
):
    response = await client.patch(
        f"/api/queue/{reception_queue_entry.queue_entry_id}/call",
        headers=receptionist_token_headers,  # FIX: Passes token authorization header map
    )

    assert response.status_code == 200

    data = response.json()
    assert data["queue_entry_id"] == str(reception_queue_entry.queue_entry_id)
    assert data["status"] == "CALLED"



@pytest.mark.asyncio
async def test_staff_cannot_call_second_patient_while_first_is_active(
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff = reception_context["staff"]

    patient1 = await patient_factory()
    patient2 = await patient_factory()

    visit1 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient1.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="First Visit",
        )
    )
    visit2 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient2.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Second Visit",
        )
    )

    entry1 = await services["queue"].create_queue_entry(
        visit_id=visit1.visit_id,
        dept_id=reception.dept_id,
    )
    entry2 = await services["queue"].create_queue_entry(
        visit_id=visit2.visit_id,
        dept_id=reception.dept_id,
    )

    await services["queue"].call_queue_entry(
        entry1.queue_entry_id,
        staff_id=staff.staff_id,
    )

    with pytest.raises(HTTPException) as exc:
        await services["queue"].call_queue_entry(
            entry2.queue_entry_id,
            staff_id=staff.staff_id,
        )

    assert exc.value.status_code == 409




@pytest.mark.asyncio
async def test_second_staff_cannot_claim_already_called_patient(
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff_a = reception_context["staff"]

    # Create another staff member in the same department
    staff_b = Staff(
        staff_id=uuid4(),
        employee_id="REC002",
        first_name="Bob",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        dept_id=reception.dept_id,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )

    reception_context["db"].add(staff_b)
    await reception_context["db"].commit()

    patient = await patient_factory()

    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Reception Check-in",
        )
    )

    entry = await services["queue"].create_queue_entry(
        visit_id=visit.visit_id,
        dept_id=reception.dept_id,
    )

    await services["queue"].call_queue_entry(
        entry.queue_entry_id,
        staff_id=staff_a.staff_id,
    )

    with pytest.raises(HTTPException) as exc:
        await services["queue"].call_queue_entry(
            entry.queue_entry_id,
            staff_id=staff_b.staff_id,
        )

    assert exc.value.status_code == 422

@pytest.mark.asyncio
async def test_staff_cannot_start_patient_owned_by_another_staff(
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff_a = reception_context["staff"]

    staff_b = Staff(
        staff_id=uuid4(),
        employee_id="REC003",
        first_name="Charlie",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        dept_id=reception.dept_id,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )

    reception_context["db"].add(staff_b)
    await reception_context["db"].commit()

    patient = await patient_factory()

    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Reception Check-in",
        )
    )

    entry = await services["queue"].create_queue_entry(
        visit_id=visit.visit_id,
        dept_id=reception.dept_id,
    )

    await services["queue"].call_queue_entry(
        entry.queue_entry_id,
        staff_id=staff_a.staff_id,
    )

    with pytest.raises(HTTPException) as exc:
        await services["queue"].start_queue_entry(
            entry.queue_entry_id,
            staff_id=staff_b.staff_id,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_staff_can_call_another_patient_after_completion(
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff = reception_context["staff"]

    patient1 = await patient_factory()
    patient2 = await patient_factory()

    visit1 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient1.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="First Check-in",
        )
    )
    visit2 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient2.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Second Check-in",
        )
    )

    entry1 = await services["queue"].create_queue_entry(
        visit_id=visit1.visit_id,
        dept_id=reception.dept_id,
    )
    entry2 = await services["queue"].create_queue_entry(
        visit_id=visit2.visit_id,
        dept_id=reception.dept_id,
    )

    await services["queue"].call_queue_entry(
        entry1.queue_entry_id,
        staff_id=staff.staff_id,
    )

    await services["queue"].start_queue_entry(
        entry1.queue_entry_id,
        staff_id=staff.staff_id,
    )

    await services["queue"].complete_queue_entry(
        entry1.queue_entry_id,
        staff_id=staff.staff_id,
    )

    second_entry = await services["queue"].call_queue_entry(
        entry2.queue_entry_id,
        staff_id=staff.staff_id,
    )

    assert second_entry.status == QueueEntryStatus.CALLED
    assert second_entry.assigned_staff_id == staff.staff_id

@pytest.mark.asyncio
async def test_no_show_releases_staff_for_next_patient(
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff = reception_context["staff"]

    patient1 = await patient_factory()
    patient2 = await patient_factory()

    visit1 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient1.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="First Check-in",
        )
    )
    visit2 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient2.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Second Check-in",
        )
    )

    entry1 = await services["queue"].create_queue_entry(
        visit_id=visit1.visit_id,
        dept_id=reception.dept_id,
    )
    entry2 = await services["queue"].create_queue_entry(
        visit_id=visit2.visit_id,
        dept_id=reception.dept_id,
    )

    await services["queue"].call_queue_entry(
        entry1.queue_entry_id,
        staff_id=staff.staff_id,
    )

    await services["queue"].transition_entry_status(
        entry1.queue_entry_id,
        QueueEntryStatus.NO_SHOW,
        staff_id=staff.staff_id,
    )

    second_entry = await services["queue"].call_queue_entry(
        entry2.queue_entry_id,
        staff_id=staff.staff_id,
    )

    assert second_entry.status == QueueEntryStatus.CALLED
    assert second_entry.assigned_staff_id == staff.staff_id


@pytest.mark.asyncio
async def test_call_endpoint_assigns_authenticated_staff(
    client,
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff = reception_context["staff"]

    # Generate token headers using the staff member created by reception_context
    token = create_access_token({"sub": str(staff.staff_id)})
    headers = {"Authorization": f"Bearer {token}"}

    patient = await patient_factory()
    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Reception Check-in",
        )
    )

    entry = await services["queue"].create_queue_entry(
        visit_id=visit.visit_id,
        dept_id=reception.dept_id,
    )

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/call",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "CALLED"
    assert data["assigned_staff_id"] == str(staff.staff_id)

@pytest.mark.asyncio
async def test_call_endpoint_rejects_second_active_patient(
    client,
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff = reception_context["staff"]

    token = create_access_token({"sub": str(staff.staff_id)})
    headers = {"Authorization": f"Bearer {token}"}

    patient1 = await patient_factory()
    patient2 = await patient_factory()

    visit1 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient1.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="First Check-in",
        )
    )
    visit2 = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient2.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Second Check-in",
        )
    )

    entry1 = await services["queue"].create_queue_entry(
        visit_id=visit1.visit_id,
        dept_id=reception.dept_id,
    )

    entry2 = await services["queue"].create_queue_entry(
        visit_id=visit2.visit_id,
        dept_id=reception.dept_id,
    )

    first_response = await client.patch(
        f"/api/queue/{entry1.queue_entry_id}/call",
        headers=headers,
    )

    assert first_response.status_code == 200

    second_response = await client.patch(
        f"/api/queue/{entry2.queue_entry_id}/call",
        headers=headers,
    )

    assert second_response.status_code == 409


@pytest.mark.asyncio
async def test_other_staff_cannot_start_owned_patient(
    db,
    client,
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff_a = reception_context["staff"]

    # 1. Create Staff B dynamically
    staff_b = Staff(
        staff_id=uuid4(),
        employee_id="REC002",
        dept_id=reception.dept_id,
        first_name="Bob",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff_b)
    await db.commit()
    await db.refresh(staff_b)

    # 2. Build token headers for both staff members
    headers_a = {"Authorization": f"Bearer {create_access_token({'sub': str(staff_a.staff_id)})}"}
    headers_b = {"Authorization": f"Bearer {create_access_token({'sub': str(staff_b.staff_id)})}"}

    patient = await patient_factory()
    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Reception Check-in",
        )
    )

    entry = await services["queue"].create_queue_entry(
        visit_id=visit.visit_id,
        dept_id=reception.dept_id,
    )

    # Staff A claims the patient
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/call",
        headers=headers_a,
    )
    assert response.status_code == 200

    # Staff B attempts to start Staff A's patient
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
        headers=headers_b,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_other_staff_cannot_mark_owned_patient_no_show(
    db,
    client,
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff_a = reception_context["staff"]

    # 1. Create Staff B dynamically
    staff_b = Staff(
        staff_id=uuid4(),
        employee_id="REC002",
        dept_id=reception.dept_id,
        first_name="Bob",
        last_name="Receptionist",
        role=StaffRole.RECEPTIONIST,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(staff_b)
    await db.flush()  # Use flush instead of commit to keep fixture transaction open

    headers_a = {
        "Authorization": f"Bearer {create_access_token({'sub': str(staff_a.staff_id)})}"
    }
    headers_b = {
        "Authorization": f"Bearer {create_access_token({'sub': str(staff_b.staff_id)})}"
    }

    patient = await patient_factory()
    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Reception Check-in",
        )
    )

    entry = await services["queue"].create_queue_entry(
        visit_id=visit.visit_id,
        dept_id=reception.dept_id,
    )

    # Commit/flush so the API HTTP client can see the entry in the DB session
    await db.commit()

    # Staff A claims the patient
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/call",
        headers=headers_a,
    )
    assert response.status_code == 200

    # Staff B attempts to mark Staff A's patient as no-show
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/no-show",
        headers=headers_b,
    )

    # Print body if it fails to see the actual error message
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.json()}"


@pytest.mark.asyncio
async def test_owner_can_complete_patient(
    client,
    reception_context,
    patient_factory,
):
    services = reception_context["services"]
    reception = reception_context["reception"]
    staff = reception_context["staff"]

    token = create_access_token({"sub": str(staff.staff_id)})
    headers = {"Authorization": f"Bearer {token}"}

    patient = await patient_factory()
    visit = await services["visit"].start_visit(
        VisitCreate(
            patient_id=patient.patient_id,
            entry_type=EntryType.WALK_IN,
            visit_reason="Reception Check-in",
        )
    )

    entry = await services["queue"].create_queue_entry(
        visit_id=visit.visit_id,
        dept_id=reception.dept_id,
    )

    # Call patient
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/call",
        headers=headers,
    )
    assert response.status_code == 200, response.json()

    # Start consultation
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/start",
        headers=headers,
    )
    assert response.status_code == 200, response.json()

    # Complete consultation
    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/complete",
        headers=headers,
    )

    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_staff_sees_only_own_no_show_entries(
    client,
    db,
    receptionist,
    receptionist_two,
    create_no_show_entry,
):
    entry_one = await create_no_show_entry(
        assigned_staff_id=receptionist.staff_id,
    )

    entry_two = await create_no_show_entry(
        assigned_staff_id=receptionist_two.staff_id,
    )

    response = await client.get(
        f"/api/queue/department/{entry_one.dept_id}/no-show",
        headers={
            "Authorization": f"Bearer {receptionist.access_token}"
        },
    )

    assert response.status_code == 200

    entries = response.json()

    ids = {
        entry["queue_entry_id"]
        for entry in entries
    }

    assert str(entry_one.queue_entry_id) in ids
    assert str(entry_two.queue_entry_id) not in ids


@pytest.mark.asyncio
async def test_second_staff_sees_only_their_own_no_show(
    client,
    receptionist,
    receptionist_two,
    create_no_show_entry,
):
    entry_one = await create_no_show_entry(
        assigned_staff_id=receptionist.staff_id,
    )

    entry_two = await create_no_show_entry(
        assigned_staff_id=receptionist_two.staff_id,
    )

    response = await client.get(
        f"/api/queue/department/{entry_one.dept_id}/no-show",
        headers={
            "Authorization": f"Bearer {receptionist_two.access_token}"
        },
    )

    assert response.status_code == 200

    entries = response.json()

    ids = {
        entry["queue_entry_id"]
        for entry in entries
    }

    assert str(entry_two.queue_entry_id) in ids
    assert str(entry_one.queue_entry_id) not in ids


@pytest.mark.asyncio
async def test_staff_can_requeue_own_no_show(
    client,
    db,
    receptionist,
    create_no_show_entry,
):
    entry = await create_no_show_entry(
        assigned_staff_id=receptionist.staff_id,
    )

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
        headers={"Authorization": f"Bearer {receptionist.access_token}"},
    )

    assert response.status_code == 200, response.json()

    data = response.json()
    assert data["status"] == "WAITING"
    assert data["assigned_staff_id"] is None

    # Fetch updated state directly to avoid fixture session detachment issues
    updated_entry = await db.get(QueueEntry, entry.queue_entry_id)

    assert updated_entry.status == QueueEntryStatus.WAITING
    assert updated_entry.assigned_staff_id is None

@pytest.mark.asyncio
async def test_other_staff_cannot_requeue_no_show(
    client,
    db,
    receptionist,
    receptionist_two,
    create_no_show_entry,
):
    entry = await create_no_show_entry(
        assigned_staff_id=receptionist.staff_id,
    )

    response = await client.patch(
        f"/api/queue/{entry.queue_entry_id}/requeue",
        headers={
            "Authorization": f"Bearer {receptionist_two.access_token}"
        },
    )

    assert response.status_code == 403

    await db.refresh(entry)

    assert entry.status == QueueEntryStatus.NO_SHOW
    assert entry.assigned_staff_id == receptionist.staff_id