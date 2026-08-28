from uuid import uuid4
import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient

from app.domain.models.models import (
    QueueEntry,
    VisitStage,
    EntryType,
    Department,
    DeptType,
    QueueEntryStatus,
    StaffRole,
)
from app.domain.services import auth_service
from app.core.security import create_access_token
from app.domain.models.models import Staff, StaffRole


pytestmark = pytest.mark.asyncio


# ── LOCAL FIXTURES ───────────────────────────────────────────────────────────

from sqlalchemy import select

@pytest_asyncio.fixture
async def setup_departments(db):
    """
    Creates (or reuses) the core hospital routing departments.
    """

    department_definitions = {
        "RECEPTION": {
            "name": "Reception",
            "type": DeptType.OPD,
        },
        "TRIAGE": {
            "name": "Triage",
            "type": DeptType.OPD,
        },
         "CONSULT": {
            "name": "Consultation",
            "type": DeptType.OPD,
        },
        "EMERGENCY": {
            "name": "Emergency",
            "type": DeptType.EMERGENCY,
        },
    }

    departments = {}

    for code, values in department_definitions.items():

        result = await db.execute(
            select(Department).where(
                Department.department_code == code
            )
        )

        dept = result.scalar_one_or_none()

        if dept is None:
            dept = Department(
                department_code=code,
                name=values["name"],
                type=values["type"],
                is_active=True,
            )

            db.add(dept)
            await db.flush()

        departments[code] = dept

    await db.commit()

    for dept in departments.values():
        await db.refresh(dept)

    return departments

@pytest.fixture
async def receptionist(db, department):
    staff = Staff(
        employee_id="REC001",
        first_name="Reception",
        last_name="User",
        role=StaffRole.RECEPTIONIST,
        dept_id=department.dept_id,
        hashed_password="ignored",
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    return staff


@pytest.fixture
async def receptionist_headers(receptionist):
    return make_headers(receptionist)


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


@pytest.fixture
async def doctor_headers(doctor):
    return make_headers(doctor)


@pytest.fixture
async def nurse(db, department):
    staff = Staff(
        employee_id="NUR001",
        first_name="Nurse",
        last_name="User",
        role=StaffRole.NURSE,
        dept_id=department.dept_id,
        hashed_password="ignored",
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    return staff


@pytest.fixture
async def nurse_headers(nurse):
    return make_headers(nurse)

@pytest.fixture
async def triage_nurse(db, department):
    staff = Staff(
        employee_id="TRI001",
        first_name="Triage",
        last_name="Nurse",
        role=StaffRole.TRIAGE_NURSE,
        dept_id=department.dept_id,
        hashed_password="ignored",
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    return staff


@pytest.fixture
async def triage_headers(triage_nurse):
    return make_headers(triage_nurse)

@pytest.fixture
async def admin_staff(db, department):
    staff = Staff(
        employee_id="ADM001",
        first_name="Admin",
        last_name="User",
        role=StaffRole.ADMIN,
        dept_id=department.dept_id,
        hashed_password="ignored",
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    return staff


@pytest.fixture
async def admin_headers(admin_staff):
    return make_headers(admin_staff)



def make_headers(staff: Staff):
    token = create_access_token(
        {
            "sub": str(staff.staff_id),
            "employee_id": staff.employee_id,
            "role": staff.role.value,
            "dept_id": str(staff.dept_id),
        }
    )

    return {
        "Authorization": f"Bearer {token}"
    }

# ── GROUP 1: KIOSK DISPATCH ──────────────────────────────────────────────────

async def test_dispatch_walkin_routes_to_reception(
    client: AsyncClient, db, active_visit, setup_departments
):
    """POST /api/routing/dispatch/{visit_id} - Walk-in routes to RECEPTION."""
    active_visit.visit_type = EntryType.WALK_IN
    await db.commit()

    response = await client.post(f"/api/routing/dispatch/{active_visit.visit_id}")
    assert response.status_code == status.HTTP_201_CREATED

    reception_dept = setup_departments["RECEPTION"]
    data = response.json()
    assert data["department_id"] == str(reception_dept.dept_id)




async def test_dispatch_appointment_routes_to_triage(
    client: AsyncClient,
    db,
    active_visit,
    setup_departments,
):
    """
    Appointment visits should bypass reception and go directly to Triage.
    """

    active_visit.entry_type = EntryType.APPOINTMENT

    await db.commit()
    await db.refresh(active_visit)

    response = await client.post(
        f"/api/routing/dispatch/{active_visit.visit_id}"
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()

    assert data["visit_id"] == str(active_visit.visit_id)

    assert data["department_id"] == str(
        setup_departments["TRIAGE"].dept_id
    )


async def test_dispatch_emergency_routes_to_emergency(
    client: AsyncClient,
    db,
    active_visit,
    setup_departments,
):
    """
    Emergency visits should bypass every department and route
    directly to Emergency.
    """

    active_visit.entry_type = EntryType.EMERGENCY

    await db.commit()
    await db.refresh(active_visit)

    response = await client.post(
        f"/api/routing/dispatch/{active_visit.visit_id}"
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()

    assert data["visit_id"] == str(active_visit.visit_id)

    assert data["department_id"] == str(
        setup_departments["EMERGENCY"].dept_id
    )

async def test_dispatch_referral_routes_to_reception(
    client: AsyncClient,
    db,
    active_visit,
    setup_departments,
):
    """
    Referral patients currently follow the standard reception workflow.
    """

    active_visit.entry_type = EntryType.REFERRAL

    await db.commit()
    await db.refresh(active_visit)

    response = await client.post(
        f"/api/routing/dispatch/{active_visit.visit_id}"
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()

    assert data["visit_id"] == str(active_visit.visit_id)

    assert data["department_id"] == str(
        setup_departments["RECEPTION"].dept_id
    )


async def test_dispatch_referral_routes_to_reception(
    client: AsyncClient, db, active_visit, setup_departments
):
    """POST /api/routing/dispatch/{visit_id} - Referral routes to RECEPTION."""
    active_visit.EntryType = EntryType.REFERRAL
    await db.commit()

    response = await client.post(f"/api/routing/dispatch/{active_visit.visit_id}")
    assert response.status_code == status.HTTP_201_CREATED

    reception_dept = setup_departments["RECEPTION"]
    data = response.json()
    assert data["department_id"] == str(reception_dept.dept_id)


async def test_dispatch_visit_not_found(client: AsyncClient, setup_departments):
    """POST /api/routing/dispatch/{visit_id} - 404 for unknown visit_id."""
    response = await client.post(f"/api/routing/dispatch/{uuid4()}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_dispatch_invalid_uuid(client: AsyncClient):
    """POST /api/routing/dispatch/{visit_id} - 422 for malformed UUID."""
    response = await client.post("/api/routing/dispatch/invalid-uuid-format")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_dispatch_completed_visit_fails(
    client: AsyncClient, db, active_visit, setup_departments
):
    """POST /api/routing/dispatch/{visit_id} - 409 Conflict for non-active visit."""
    active_visit.stage = VisitStage.COMPLETED
    await db.commit()

    response = await client.post(f"/api/routing/dispatch/{active_visit.visit_id}")
    assert response.status_code == status.HTTP_409_CONFLICT


# ── GROUP 2: MOVE PATIENT ────────────────────────────────────────────────────


async def test_dispatch_rejects_an_invalid_kiosk_api_key(
    client: AsyncClient,
):
    """Kiosk dispatch is unavailable without the managed-device secret."""
    response = await client.post(
        f"/api/routing/dispatch/{uuid4()}",
        headers={"X-Kiosk-API-Key": "invalid-key"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

async def test_move_patient_success(
    client,
    db,
    active_visit,
    queue_entry,
    doctor_staff,
    doctor_token_headers,
    setup_departments,
):
    queue_entry.status = QueueEntryStatus.IN_PROGRESS
    queue_entry.assigned_staff_id = doctor_staff.staff_id

    await db.commit()

    target_dept = setup_departments["TRIAGE"]

    payload = {
        "target_department_id": str(target_dept.dept_id),
        "priority": "NORMAL",
        "notes": "Transferring to triage",
    }

    response = await client.post(
        f"/api/routing/move/{active_visit.visit_id}",
        json=payload,
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["department_id"] == str(target_dept.dept_id)
    assert data["visit_id"] == str(active_visit.visit_id)
    assert data["status"] == "WAITING"
    assert data["priority"] == "NORMAL"
    assert data["notes"] == "Transferring to triage"




async def test_move_patient_inactive_department(
    client: AsyncClient, db, active_visit, queue_entry, doctor_token_headers, setup_departments
):
    """POST /api/routing/move/{visit_id} - 400 for inactive target department."""
    queue_entry.status = QueueEntryStatus.IN_PROGRESS
    target_dept = setup_departments["TRIAGE"]
    target_dept.is_active = False
    await db.commit()

    payload = {"target_department_id": str(target_dept.dept_id)}

    response = await client.post(
        f"/api/routing/move/{active_visit.visit_id}", json=payload, headers=doctor_token_headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_move_patient_visit_not_found(
    client: AsyncClient, doctor_token_headers, setup_departments
):
    """POST /api/routing/move/{visit_id} - 404 for unknown visit_id."""
    target_dept = setup_departments["TRIAGE"]
    payload = {"target_department_id": str(target_dept.dept_id)}

    response = await client.post(
        f"/api/routing/move/{uuid4()}", json=payload, headers=doctor_token_headers
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_move_patient_invalid_uuid(client: AsyncClient, doctor_token_headers):
    """POST /api/routing/move/{visit_id} - 422 for malformed UUID."""
    response = await client.post(
        "/api/routing/move/invalid-uuid-format", json={}, headers=doctor_token_headers
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_move_patient_token_preservation_regression(
    client: AsyncClient,
    db,
    active_visit,
    queue_entry,
    doctor_staff,
    doctor_token_headers,
    setup_departments,
):
    queue_entry.status = QueueEntryStatus.IN_PROGRESS
    queue_entry.assigned_staff_id = doctor_staff.staff_id

    old_token = active_visit.token_number

    await db.commit()

    target_dept = setup_departments["TRIAGE"]

    response = await client.post(
        f"/api/routing/move/{active_visit.visit_id}",
        json={"target_department_id": str(target_dept.dept_id)},
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(active_visit)

    assert active_visit.token_number == old_token


async def test_move_patient_forbidden_role(
    client,
    active_visit,
    admin_headers,
    setup_departments,
):
    target = setup_departments["TRIAGE"]

    payload = {
        "target_department_id": str(target.dept_id)
    }

    response = await client.post(
        f"/api/routing/move/{active_visit.visit_id}",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

async def test_get_current_location_success(
    client: AsyncClient,
    active_visit,
    queue_entry,
    receptionist_token_headers,
):
    """
    GET /api/routing/location/{visit_id}
    Returns the patient's current routing location.
    """

    response = await client.get(
        f"/api/routing/location/{active_visit.visit_id}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["visit_id"] == str(active_visit.visit_id)
    assert data["token_number"] == active_visit.token_number

    assert "current_department_name" in data
    assert "position_in_line" in data
    assert "estimated_wait_minutes" in data

async def test_get_current_location_no_active_queue(
    client: AsyncClient,
    db,
    active_visit,
    receptionist_token_headers,
):
    """
    GET /api/routing/location/{visit_id}

    Visit exists but has no active queue entry.
    """

    active_visit.current_queue_entry_id = None
    await db.commit()

    response = await client.get(
        f"/api/routing/location/{active_visit.visit_id}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["visit_id"] == str(active_visit.visit_id)
    assert data["token_number"] == active_visit.token_number
    assert data["visit_stage"] == VisitStage.ACTIVE.value

    assert data["current_queue_entry_id"] is None
    assert data["current_department_id"] is None
    assert data["current_department_name"] is None

    assert data["status"] is None

    assert data["position_in_line"] == 0
    assert data["estimated_wait_minutes"] == 0

    assert data["assigned_staff_id"] is None
    assert data["entered_at"] is None

async def test_get_current_location_visit_not_found(
    client: AsyncClient,
    receptionist_token_headers,
):
    response = await client.get(
        f"/api/routing/location/{uuid4()}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_get_current_location_invalid_uuid(
    client: AsyncClient,
    receptionist_token_headers,
):
    response = await client.get(
        "/api/routing/location/not-a-valid-uuid",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_get_current_location_unauthorized(
    client: AsyncClient,
    active_visit,
):
    response = await client.get(
        f"/api/routing/location/{active_visit.visit_id}"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_patient_history_success(
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

    response = await client.get(
        f"/api/routing/history/{active_visit.visit_id}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1

    entry = data[0]

    assert entry["visit_id"] == str(active_visit.visit_id)
    assert entry["queue_entry_id"] == str(queue_entry.queue_entry_id)

async def test_get_patient_history_ordered(
    client: AsyncClient,
    db,
    active_visit,
    receptionist_token_headers,
):
    """
    Queue history should be returned in chronological order.
    """

    response = await client.get(
        f"/api/routing/history/{active_visit.visit_id}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    entered_times = [entry["entered_at"] for entry in data]

    assert entered_times == sorted(entered_times)

async def test_get_patient_history_visit_not_found(
    client: AsyncClient,
    receptionist_token_headers,
):
    """
    Unknown visit returns 404.
    """

    response = await client.get(
        f"/api/routing/history/{uuid4()}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_get_patient_history_invalid_uuid(
    client: AsyncClient,
    receptionist_token_headers,
):
    """
    Invalid UUID returns validation error.
    """

    response = await client.get(
        "/api/routing/history/not-a-uuid",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

async def test_get_patient_history_unauthorized(
    client: AsyncClient,
    active_visit,
):
    """
    Missing JWT returns 401.
    """

    response = await client.get(
        f"/api/routing/history/{active_visit.visit_id}"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_get_patient_history_unauthorized(
    client: AsyncClient,
    active_visit,
):
    """
    Missing JWT returns 401.
    """

    response = await client.get(
        f"/api/routing/history/{active_visit.visit_id}"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_get_patient_history_response_schema(
    client: AsyncClient,
    active_visit,
    queue_entry,
    receptionist_token_headers,
):
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
        "department_id",
        "status",
        "priority",
        "entered_at",
    }

    assert expected_fields.issubset(entry.keys())


# ── GROUP 2: PATIENT TRANSFER / ROUTING ──────────────────────────────────────


async def test_transfer_patient_success(
    client: AsyncClient,
    db,
    active_visit,
    setup_departments,
    doctor_token_headers,
    doctor_staff,
):
    """
    A doctor transfers an in-progress patient to another department.

    Expected:
        Current QueueEntry -> COMPLETED
        New QueueEntry      -> WAITING
        Visit               -> ACTIVE
    """
    from sqlalchemy import select
    from app.domain.models.models import QueueEntry, QueueEntryStatus, VisitStage

    # 1. Retrieve the existing active QueueEntry created by active_visit fixture
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )
    current_entry = result.scalar_one()

    # 2. Update its status to IN_PROGRESS to simulate an ongoing consultation
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    current_entry.assigned_staff_id = doctor_staff.staff_id
    await db.commit()

    # 3. Transfer payload to target department
    target_department = setup_departments["CONSULT"]

    payload = {
        "target_department_id": str(target_department.dept_id),
        "reason": "DEPARTMENT_TRANSFER",
        "priority": "NORMAL",
        "notes": "Patient requires further clinical assessment.",
    }

    # 4. Act
    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        json=payload,
        headers=doctor_token_headers,
    )

    # 5. Assert HTTP response
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["visit_id"] == str(active_visit.visit_id)
    assert data["department_id"] == str(target_department.dept_id)
    assert data["status"] == QueueEntryStatus.WAITING.value

    # 6. Assert current queue entry was marked COMPLETED
    await db.refresh(current_entry)
    assert current_entry.status == QueueEntryStatus.COMPLETED

    # 7. Assert Visit remains ACTIVE
    await db.refresh(active_visit)
    assert active_visit.stage == VisitStage.ACTIVE

    # 8. Assert new destination QueueEntry exists in WAITING state
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id,
            QueueEntry.department_id == target_department.dept_id,
        )
    )
    new_entry = result.scalar_one()
    assert new_entry.status == QueueEntryStatus.WAITING


async def test_transfer_waiting_patient_rejected(
    client: AsyncClient,
    db,
    active_visit,
    setup_departments,
    doctor_token_headers,
):
    """
    A patient must be actively in an encounter before being transferred.
    """
    from sqlalchemy import select
    from app.domain.models.models import QueueEntry

    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )

    current_entry = result.scalar_one()

    assert current_entry.status == QueueEntryStatus.WAITING

    # Matches key in setup_departments fixture
    target_department = setup_departments["CONSULT"]

    payload = {
        "target_department_id": str(target_department.dept_id),
        "reason": "DEPARTMENT_TRANSFER",
        "priority": "NORMAL",
        "notes": "Transfer attempt.",
    }

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        json=payload,
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT

    assert (
        "in-progress" in response.json()["detail"].lower()
        or "started" in response.json()["detail"].lower()
    )


async def test_transfer_to_same_department_rejected(
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
    from sqlalchemy import select
    from app.domain.models.models import QueueEntry, QueueEntryStatus

    # 1. Fetch the QueueEntry automatically created with active_visit
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )
    current_entry = result.scalar_one()

    # 2. Transition it to IN_PROGRESS so it simulates an active encounter
    current_entry.status = QueueEntryStatus.IN_PROGRESS
    await db.commit()

    # 3. Payload targeting the same department
    payload = {
        "target_department_id": str(current_entry.department_id),
        "reason": "DEPARTMENT_TRANSFER",
        "priority": "NORMAL",
        "notes": "Invalid same-department transfer.",
    }

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        json=payload,
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert (
        response.json()["detail"]
        == "Patient is already queued in the target department."
    )


async def test_transfer_to_inactive_department_rejected(
    client: AsyncClient,
    db,
    active_visit,
    setup_departments,
    doctor_token_headers,
):
    """
    Transfers to inactive departments must be rejected.
    """
    from sqlalchemy import select
    from app.domain.models.models import QueueEntry, QueueEntryStatus

    # Fetch active visit entry and transition to IN_PROGRESS
    result = await db.execute(
        select(QueueEntry).where(
            QueueEntry.visit_id == active_visit.visit_id
        )
    )
    current_entry = result.scalar_one()
    current_entry.status = QueueEntryStatus.IN_PROGRESS

    # Deactivate the target department
    target_department = setup_departments["CONSULT"]
    target_department.is_active = False

    await db.commit()

    payload = {
        "target_department_id": str(target_department.dept_id),
        "reason": "DEPARTMENT_TRANSFER",
        "priority": "NORMAL",
        "notes": "Transfer to inactive department.",
    }

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        json=payload,
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    assert (
        "inactive" in response.json()["detail"].lower()
        or "does not exist" in response.json()["detail"].lower()
    )

async def test_transfer_requires_authentication(
    client: AsyncClient,
    active_visit,
    setup_departments,
):
    """
    An unauthenticated client cannot transfer a patient.
    """

    target_department = setup_departments["CONSULT"]

    payload = {
        "target_department_id": str(target_department.dept_id),
        "reason": "DEPARTMENT_TRANSFER",
        "priority": "NORMAL",
        "notes": "Unauthorized transfer attempt.",
    }

    response = await client.post(
        f"/api/routing/{active_visit.visit_id}/transfer",
        json=payload,
    )

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )