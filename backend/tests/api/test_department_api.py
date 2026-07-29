from uuid import uuid4
from app.domain.models.models import Department, DeptType
import pytest
from httpx import AsyncClient
from fastapi import status

pytestmark = pytest.mark.asyncio

# ============================================================================
# GROUP 1: CREATE DEPARTMENT (/api/departments)
# ============================================================================


async def test_create_department_success(
    client: AsyncClient,
    admin_headers: dict,
):
    """POST /api/departments - Admin creates a new department successfully."""
    payload = {
        "name": "Radiology",
        "department_code": "RAD",
        "type": "OPD",
        "max_capacity": 30,
    }

    response = await client.post(
        "/api/departments",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert "dept_id" in data
    assert data["name"] == "Radiology"
    assert data["department_code"] == "RAD"
    assert data["type"] == "OPD"
    assert data["is_active"] is True
    assert data["max_capacity"] == 30


async def test_create_department_duplicate_code(
    client: AsyncClient,
    department,
    admin_headers: dict,
):
    """POST /api/departments - Fails with 409 Conflict when department code already exists."""
    payload = {
        "name": "Another Reception",
        "department_code": department.department_code,
        "type": "OPD",
        "max_capacity": 40,
    }

    response = await client.post(
        "/api/departments",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_create_department_validation_error(
    client: AsyncClient,
    admin_headers: dict,
):
    """POST /api/departments - Fails with 422 Unprocessable Entity when required fields are missing."""
    payload = {
        "name": "",
    }

    response = await client.post(
        "/api/departments",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_create_department_unauthorized(
    client: AsyncClient,
):
    """POST /api/departments - Fails with 401 Unauthorized when no auth headers are provided."""
    payload = {
        "name": "Radiology",
        "department_code": "RAD",
        "type": "OPD",
        "max_capacity": 20,
    }

    response = await client.post(
        "/api/departments",
        json=payload,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_create_department_forbidden_role(
    client: AsyncClient,
    doctor_token_headers: dict,
):
    """POST /api/departments - Fails with 403 Forbidden when authenticated user is not an ADMIN."""
    payload = {
        "name": "Radiology",
        "department_code": "RAD",
        "type": "OPD",
        "max_capacity": 20,
    }

    response = await client.post(
        "/api/departments",
        json=payload,
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

# ============================================================================
# GROUP 2: READ DEPARTMENTS (/api/departments)
# ============================================================================

# --- 1. GET /api/departments ---


async def test_get_departments_success(
    client: AsyncClient,
    admin_headers,
    department,
):
    """GET /api/departments - Returns all departments."""

    response = await client.get(
        "/api/departments",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1

    assert data[0]["dept_id"] == str(department.dept_id)




async def test_get_departments_unauthorized(
    client: AsyncClient,
):
    """GET /api/departments - Requires authentication."""

    response = await client.get("/api/departments")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_departments_response_schema(
    client: AsyncClient,
    admin_headers,
    department,
):
    """GET /api/departments - Response matches DepartmentRead."""

    response = await client.get(
        "/api/departments",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    item = response.json()[0]

    assert "dept_id" in item
    assert "name" in item
    assert "department_code" in item
    assert "type" in item
    assert "is_active" in item
    assert "max_capacity" in item


# --- 2. GET /api/departments/active ---


async def test_get_active_departments_success(
    client: AsyncClient,
    admin_headers,
    department,
):
    """GET /api/departments/active - Returns active departments."""

    response = await client.get(
        "/api/departments/active",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert len(data) >= 1

    assert all(d["is_active"] for d in data)


async def test_get_active_departments_filters_inactive(
    client: AsyncClient,
    db,
    admin_headers,
    department,
):
    """GET /api/departments/active - Does not return inactive departments."""

    department.is_active = False

    await db.commit()

    response = await client.get(
        "/api/departments/active",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    assert response.json() == []


async def test_get_active_departments_unauthorized(
    client: AsyncClient,
):
    response = await client.get("/api/departments/active")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 3. GET /api/departments/{department_id} ---


async def test_get_department_success(
    client: AsyncClient,
    admin_headers,
    department,
):
    """GET /api/departments/{id}"""

    response = await client.get(
        f"/api/departments/{department.dept_id}",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["dept_id"] == str(department.dept_id)
    assert data["department_code"] == department.department_code


async def test_get_department_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.get(
        f"/api/departments/{uuid4()}",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_get_department_invalid_uuid(
    client: AsyncClient,
    admin_headers,
):
    response = await client.get(
        "/api/departments/not-a-uuid",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_get_department_unauthorized(
    client: AsyncClient,
    department,
):
    response = await client.get(
        f"/api/departments/{department.dept_id}"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# GROUP 3: UPDATE DEPARTMENT (PATCH /api/departments/{department_id})
# ============================================================================


async def test_update_department_success(
    client: AsyncClient,
    admin_headers,
    department,
):
    """PATCH /api/departments/{id} - Successfully updates a department."""

    payload = {
        "name": "Radiology Updated",
        "max_capacity": 75,
    }

    response = await client.patch(
        f"/api/departments/{department.dept_id}",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["name"] == "Radiology Updated"
    assert data["max_capacity"] == 75


async def test_update_department_partial(
    client: AsyncClient,
    admin_headers,
    department,
):
    """PATCH updates only supplied fields."""

    original_capacity = department.max_capacity

    payload = {
        "name": "New Reception",
    }

    response = await client.patch(
        f"/api/departments/{department.dept_id}",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["name"] == "New Reception"
    assert data["max_capacity"] == original_capacity


async def test_update_department_duplicate_code(
    client: AsyncClient,
    db,
    admin_headers,
    department,
):
    """Cannot update to an existing department code."""

    duplicate = Department(
        name="Radiology",
        department_code="RAD",
        type=DeptType.OPD,
    )

    db.add(duplicate)
    await db.commit()

    response = await client.patch(
        f"/api/departments/{department.dept_id}",
        json={"department_code": "RAD"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_update_department_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        f"/api/departments/{uuid4()}",
        json={"name": "Updated"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_update_department_invalid_uuid(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        "/api/departments/not-a-uuid",
        json={"name": "Updated"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_update_department_validation_error(
    client: AsyncClient,
    admin_headers,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}",
        json={
            "max_capacity": -1,
        },
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_update_department_unauthorized(
    client: AsyncClient,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}",
        json={"name": "Updated"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_update_department_forbidden_role(
    client: AsyncClient,
    receptionist_token_headers,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}",
        json={"name": "Updated"},
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

# ============================================================================
# GROUP 4: ACTIVATE DEPARTMENT (PATCH /api/departments/{department_id}/activate)
# ============================================================================


async def test_activate_department_success(
    client: AsyncClient,
    db,
    admin_headers,
    department,
):
    """PATCH /api/departments/{id}/activate"""

    department.is_active = False
    await db.commit()

    response = await client.patch(
        f"/api/departments/{department.dept_id}/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_active"] is True


async def test_activate_department_already_active(
    client: AsyncClient,
    admin_headers,
    department,
):
    """Activating an already active department should succeed."""

    response = await client.patch(
        f"/api/departments/{department.dept_id}/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    assert response.json()["is_active"] is True


async def test_activate_department_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        f"/api/departments/{uuid4()}/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_activate_department_invalid_uuid(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        "/api/departments/not-a-uuid/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_activate_department_unauthorized(
    client: AsyncClient,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}/activate",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_activate_department_forbidden_role(
    client: AsyncClient,
    receptionist_token_headers,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}/activate",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# GROUP 5: DEACTIVATE DEPARTMENT (PATCH /api/departments/{department_id}/deactivate)
# ============================================================================


async def test_deactivate_department_success(
    client: AsyncClient,
    admin_headers,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["is_active"] is False


async def test_deactivate_department_already_inactive(
    client: AsyncClient,
    db,
    admin_headers,
    department,
):
    department.is_active = False
    await db.commit()

    response = await client.patch(
        f"/api/departments/{department.dept_id}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    assert response.json()["is_active"] is False


async def test_deactivate_department_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        f"/api/departments/{uuid4()}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_deactivate_department_invalid_uuid(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        "/api/departments/not-a-uuid/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_deactivate_department_unauthorized(
    client: AsyncClient,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}/deactivate",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_deactivate_department_forbidden_role(
    client: AsyncClient,
    receptionist_token_headers,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}/deactivate",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_deactivate_department_persists_change(
    client: AsyncClient,
    db,
    admin_headers,
    department,
):
    response = await client.patch(
        f"/api/departments/{department.dept_id}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(department)

    assert department.is_active is False


async def test_activate_department_persists_change(
    client: AsyncClient,
    db,
    admin_headers,
    department,
):
    department.is_active = False
    await db.commit()

    response = await client.patch(
        f"/api/departments/{department.dept_id}/activate",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(department)

    assert department.is_active is True