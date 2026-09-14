from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import AsyncClient
from fastapi import status

from app.domain.models.models import Staff, StaffRole
from app.core.security import hash_password

pytestmark = pytest.mark.asyncio

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def existing_staff(db, department):
    staff = Staff(
        employee_id="EMP001",
        first_name="John",
        last_name="Doe",
        role=StaffRole.DOCTOR,
        dept_id=department.dept_id,
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )

    db.add(staff)
    await db.commit()
    await db.refresh(staff)

    return staff


# ============================================================================
# GROUP 1: CREATE STAFF API (POST /api/staff/)
# ============================================================================


async def test_create_staff_success(
    client: AsyncClient,
    admin_headers,
    department,
):
    payload = {
        "employee_id": "EMP100",
        "first_name": "Kevin",
        "last_name": "Axel",
        "dept_id": str(department.dept_id),
        "role": "DOCTOR",
        "specialization": "Cardiology",
        "password": "Password123!",
    }

    response = await client.post(
        "/api/staff/",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()

    assert data["employee_id"] == payload["employee_id"]
    assert data["first_name"] == payload["first_name"]
    assert data["last_name"] == payload["last_name"]
    assert data["role"] == payload["role"]
    assert data["dept_id"] == payload["dept_id"]
    assert data["is_active"] is True
    assert data["is_on_duty"] is False


async def test_create_staff_duplicate_employee_id(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    payload = {
        "employee_id": existing_staff.employee_id,
        "first_name": "Jane",
        "last_name": "Smith",
        "dept_id": str(existing_staff.dept_id),
        "role": "NURSE",
        "password": "Password123!",
    }

    response = await client.post(
        "/api/staff/",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_create_staff_invalid_department(
    client: AsyncClient,
    admin_headers,
):
    payload = {
        "employee_id": "EMP999",
        "first_name": "Kevin",
        "last_name": "Axel",
        "dept_id": str(uuid4()),
        "role": "DOCTOR",
        "password": "Password123!",
    }

    response = await client.post(
        "/api/staff/",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
    )


async def test_create_staff_validation_error(
    client: AsyncClient,
    admin_headers,
):
    response = await client.post(
        "/api/staff/",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_create_staff_unauthorized(
    client: AsyncClient,
    department,
):
    payload = {
        "employee_id": "EMP101",
        "first_name": "Kevin",
        "last_name": "Axel",
        "dept_id": str(department.dept_id),
        "role": "DOCTOR",
        "password": "Password123!",
    }

    response = await client.post(
        "/api/staff/",
        json=payload,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_create_staff_forbidden_role(
    client: AsyncClient,
    doctor_token_headers,
    department,
):
    payload = {
        "employee_id": "EMP102",
        "first_name": "Kevin",
        "last_name": "Axel",
        "dept_id": str(department.dept_id),
        "role": "DOCTOR",
        "password": "Password123!",
    }

    response = await client.post(
        "/api/staff/",
        json=payload,
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

# ============================================================================
# GROUP 2: LIST STAFF API (GET /api/staff/)
# ============================================================================


async def test_get_active_staff_success(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    """
    GET /api/staff/
    Returns only active staff.
    """

    response = await client.get(
        "/api/staff/",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert len(data) >= 1

    for staff in data:
        assert staff["is_active"] is True


async def test_get_all_staff_success(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    """
    GET /api/staff/?active_only=false
    Returns every staff member.
    """

    response = await client.get(
        "/api/staff/?active_only=false",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1


async def test_get_all_staff_includes_inactive(
    client: AsyncClient,
    db,
    admin_headers,
    existing_staff,
):
    """
    active_only=false should include inactive staff.
    """

    existing_staff.is_active = False
    await db.commit()

    response = await client.get(
        "/api/staff/?active_only=false",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert any(
        staff["staff_id"] == str(existing_staff.staff_id)
        for staff in data
    )


async def test_get_active_staff_excludes_inactive(
    client: AsyncClient,
    db,
    admin_headers,
    existing_staff,
):
    """
    active_only=true excludes inactive staff.
    """

    existing_staff.is_active = False
    await db.commit()

    response = await client.get(
        "/api/staff/",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert all(
        staff["staff_id"] != str(existing_staff.staff_id)
        for staff in data
    )


async def test_get_staff_sorted(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    """
    Staff should be ordered by last name then first name.
    """

    response = await client.get(
        "/api/staff/?active_only=false",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    names = [
        (staff["last_name"], staff["first_name"])
        for staff in data
    ]

    assert names == sorted(names)


async def test_get_staff_unauthorized(
    client: AsyncClient,
):
    response = await client.get("/api/staff/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_staff_forbidden_role(
    client: AsyncClient,
    doctor_token_headers,
):
    response = await client.get(
        "/api/staff/",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

# ============================================================================
# GROUP 3: GET STAFF BY ID API (GET /api/staff/{staff_id})
# ============================================================================


async def test_get_staff_success(
    client: AsyncClient,
    doctor_token_headers,
    existing_staff,
):
    """
    GET /api/staff/{staff_id}
    Returns the requested staff member.
    """

    response = await client.get(
        f"/api/staff/{existing_staff.staff_id}",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["staff_id"] == str(existing_staff.staff_id)
    assert data["employee_id"] == existing_staff.employee_id
    assert data["first_name"] == existing_staff.first_name
    assert data["last_name"] == existing_staff.last_name
    assert data["role"] == existing_staff.role.value


async def test_get_staff_not_found(
    client: AsyncClient,
    doctor_token_headers,
):
    """
    Unknown UUID returns 404.
    """

    response = await client.get(
        f"/api/staff/{uuid4()}",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_get_staff_invalid_uuid(
    client: AsyncClient,
    doctor_token_headers,
):
    """
    Invalid UUID returns validation error.
    """

    response = await client.get(
        "/api/staff/not-a-uuid",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_get_staff_unauthorized(
    client: AsyncClient,
    existing_staff,
):
    """
    Authentication required.
    """

    response = await client.get(
        f"/api/staff/{existing_staff.staff_id}"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_staff_receptionist_allowed(
    client: AsyncClient,
    receptionist_token_headers,
    existing_staff,
):
    """
    Any authenticated user can retrieve staff information.
    """

    response = await client.get(
        f"/api/staff/{existing_staff.staff_id}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK


async def test_get_staff_response_schema(
    client: AsyncClient,
    doctor_token_headers,
    existing_staff,
):
    """
    Validates exact keys returned in the response schema.
    """

    response = await client.get(
        f"/api/staff/{existing_staff.staff_id}",
        headers=doctor_token_headers,
    )

    data = response.json()

    expected = {
        "staff_id",
        "employee_id",
        "first_name",
        "last_name",
        "role",
        "dept_id",
        "department_name",
        "department_code",
        "specialization",
        "is_on_duty",
        "is_active",
        "active_service_point_id",
    }

    assert expected == set(data.keys())

# ============================================================================
# GROUP 4: UPDATE STAFF API (PUT /api/staff/{staff_id})
# ============================================================================


async def test_update_staff_success(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    payload = {
        "first_name": "Kevin",
        "last_name": "Axel",
        "specialization": "Cyber Security",
    }

    response = await client.put(
        f"/api/staff/{existing_staff.staff_id}",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["first_name"] == "Kevin"
    assert data["last_name"] == "Axel"
    assert data["specialization"] == "Cyber Security"


async def test_update_staff_partial(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    original_last_name = existing_staff.last_name

    payload = {
        "first_name": "Updated"
    }

    response = await client.put(
        f"/api/staff/{existing_staff.staff_id}",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["first_name"] == "Updated"
    assert data["last_name"] == original_last_name


async def test_update_staff_not_found(
    client: AsyncClient,
    admin_headers,
):
    payload = {
        "first_name": "Someone"
    }

    response = await client.put(
        f"/api/staff/{uuid4()}",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_update_staff_invalid_uuid(
    client: AsyncClient,
    admin_headers,
):
    response = await client.put(
        "/api/staff/not-a-uuid",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_update_staff_validation_error(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    payload = {
        "first_name": 123
    }

    response = await client.put(
        f"/api/staff/{existing_staff.staff_id}",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_update_staff_unauthorized(
    client: AsyncClient,
    existing_staff,
):
    response = await client.put(
        f"/api/staff/{existing_staff.staff_id}",
        json={"first_name": "Kevin"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_update_staff_forbidden_role(
    client: AsyncClient,
    doctor_token_headers,
    existing_staff,
):
    response = await client.put(
        f"/api/staff/{existing_staff.staff_id}",
        json={"first_name": "Kevin"},
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_update_staff_empty_payload(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    response = await client.put(
        f"/api/staff/{existing_staff.staff_id}",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

# ============================================================================
# GROUP 5: ACTIVATE / DEACTIVATE STAFF (PATCH /api/staff/{staff_id}/...)
# ============================================================================


async def test_deactivate_staff_success(
    client: AsyncClient,
    admin_headers,
    existing_staff,
):
    response = await client.patch(
        f"/api/staff/{existing_staff.staff_id}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_active"] is False


async def test_activate_staff_success(
    client: AsyncClient,
    db,
    admin_headers,
    existing_staff,
):
    existing_staff.is_active = False
    await db.commit()

    response = await client.patch(
        f"/api/staff/{existing_staff.staff_id}/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_active"] is True


async def test_activate_staff_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        f"/api/staff/{uuid4()}/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_deactivate_staff_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        f"/api/staff/{uuid4()}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_activate_staff_invalid_uuid(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        "/api/staff/not-a-uuid/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_activate_staff_unauthorized(
    client: AsyncClient,
    existing_staff,
):
    response = await client.patch(
        f"/api/staff/{existing_staff.staff_id}/activate",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_activate_staff_forbidden_role(
    client: AsyncClient,
    doctor_token_headers,
    existing_staff,
):
    response = await client.patch(
        f"/api/staff/{existing_staff.staff_id}/activate",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# GROUP 6: MY PROFILE & DUTY STATUS API (/api/staff/me/...)
# ============================================================================

# --- 6.1: GET /api/staff/me ---


async def test_get_my_profile_success(
    client: AsyncClient,
    doctor_token_headers,
    doctor_staff,
):
    """
    GET /api/staff/me
    Returns current authenticated user's profile.
    """
    response = await client.get(
        "/api/staff/me",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["staff_id"] == str(doctor_staff.staff_id)
    assert data["employee_id"] == doctor_staff.employee_id
    assert data["role"] == doctor_staff.role.value


async def test_get_my_profile_unauthorized(
    client: AsyncClient,
):
    """
    Unauthenticated user gets 401 Unauthorized.
    """
    response = await client.get("/api/staff/me")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 6.2: POST /api/staff/me/check-in ---


async def test_check_in_success(
    client: AsyncClient,
    doctor_token_headers,
):
    """
    POST /api/staff/me/check-in
    Sets user status to on-duty.
    """
    response = await client.post(
        "/api/staff/me/check-in",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_on_duty"] is True


async def test_check_in_twice(
    client,
    doctor_token_headers,
):
    await client.post(
        "/api/staff/me/check-in",
        headers=doctor_token_headers,
    )

    response = await client.post(
        "/api/staff/me/check-in",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_check_in_unauthorized(
    client: AsyncClient,
):
    """
    Unauthenticated user cannot check in.
    """
    response = await client.post("/api/staff/me/check-in")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 6.3: POST /api/staff/me/check-out ---


async def test_check_out_success(
    client: AsyncClient,
    doctor_token_headers,
):
    """
    POST /api/staff/me/check-out
    Sets user status to off-duty.
    """
    await client.post(
        "/api/staff/me/check-in",
        headers=doctor_token_headers,
    )

    response = await client.post(
        "/api/staff/me/check-out",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_on_duty"] is False


async def test_check_out_when_off_duty(
    client: AsyncClient,
    doctor_token_headers,
):
    response = await client.post(
        "/api/staff/me/check-out",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT

    


async def test_check_out_unauthorized(
    client: AsyncClient,
):
    """
    Unauthenticated user cannot check out.
    """
    response = await client.post("/api/staff/me/check-out")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 6.4: GET /api/staff/me/status ---


async def test_my_status_off_duty(
    client: AsyncClient,
    doctor_token_headers,
):
    """
    GET /api/staff/me/status
    Reflects off-duty status when checked out.
    """
    response = await client.get(
        "/api/staff/me/status",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_on_duty"] is False


async def test_my_status_after_check_in(
    client: AsyncClient,
    doctor_token_headers,
):
    """
    GET /api/staff/me/status
    Reflects on-duty status following a check-in.
    """
    await client.post(
        "/api/staff/me/check-in",
        headers=doctor_token_headers,
    )

    response = await client.get(
        "/api/staff/me/status",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_on_duty"] is True


async def test_my_status_unauthorized(
    client: AsyncClient,
):
    """
    Unauthenticated user cannot query duty status.
    """
    response = await client.get("/api/staff/me/status")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED