"""
API tests for the admin-only staff lifecycle actions added for the
admin dashboard:

    PATCH /api/staff/{staff_id}/role            (role change)
    PATCH /api/staff/{staff_id}/transfer        (department transfer)
    PATCH /api/staff/{staff_id}/reset-password  (admin password reset)
"""
from uuid import uuid4

import pytest
from httpx import AsyncClient
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.domain.models.models import ServicePoint, Staff, StaffRole

pytestmark = pytest.mark.asyncio


# ============================================================================
# HELPERS
# ============================================================================


async def make_staff(
    db: AsyncSession,
    department,
    role: StaffRole = StaffRole.DOCTOR,
    employee_id: str | None = None,
) -> Staff:
    staff = Staff(
        employee_id=employee_id or f"EMP-{uuid4().hex[:8]}",
        first_name="Transfer",
        last_name="Target",
        role=role,
        dept_id=department.dept_id,
        hashed_password="$2b$12$unusedplaceholderhashvalue0000",
        is_active=True,
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


# ============================================================================
# GROUP 1: ROLE CHANGE (PATCH /api/staff/{staff_id}/role)
# ============================================================================


async def test_change_role_success(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/role",
        json={"role": "NURSE"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["role"] == "NURSE"
    assert data["staff_id"] == str(staff.staff_id)


async def test_change_role_persists(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    await client.patch(
        f"/api/staff/{staff.staff_id}/role",
        json={"role": "TRIAGE_NURSE"},
        headers=admin_headers,
    )

    await db.refresh(staff)
    assert staff.role == StaffRole.TRIAGE_NURSE


async def test_change_role_invalid_role_value(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/role",
        json={"role": "SUPERUSER"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_change_role_same_role_conflict(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department, role=StaffRole.DOCTOR)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/role",
        json={"role": "DOCTOR"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_change_role_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        f"/api/staff/{uuid4()}/role",
        json={"role": "NURSE"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_change_role_forbidden_for_doctor(
    client: AsyncClient,
    doctor_token_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/role",
        json={"role": "NURSE"},
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_change_role_unauthorized(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/role",
        json={"role": "NURSE"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# GROUP 2: DEPARTMENT TRANSFER (PATCH /api/staff/{staff_id}/transfer)
# ============================================================================


async def test_transfer_department_success(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    secondary_department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/transfer",
        json={"dept_id": str(secondary_department.dept_id)},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["dept_id"] == str(secondary_department.dept_id)


async def test_transfer_releases_service_point_binding(
    client: AsyncClient,
    admin_headers,
    db,
    department,
    secondary_department,
):
    staff = await make_staff(db, department)
    service_point = ServicePoint(
        dept_id=department.dept_id,
        code="DESK-01",
        label="Department desk",
    )
    db.add(service_point)
    await db.flush()
    staff.active_service_point_id = service_point.service_point_id
    await db.commit()

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/transfer",
        json={"dept_id": str(secondary_department.dept_id)},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["active_service_point_id"] is None


async def test_transfer_unknown_department_not_found(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/transfer",
        json={"dept_id": str(uuid4())},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_transfer_same_department_conflict(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/transfer",
        json={"dept_id": str(department.dept_id)},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_transfer_not_found(
    client: AsyncClient,
    admin_headers,
    department,
):
    response = await client.patch(
        f"/api/staff/{uuid4()}/transfer",
        json={"dept_id": str(department.dept_id)},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_transfer_forbidden_for_receptionist(
    client: AsyncClient,
    receptionist_token_headers,
    db,
    department,
    secondary_department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/transfer",
        json={"dept_id": str(secondary_department.dept_id)},
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# GROUP 3: ADMIN PASSWORD RESET (PATCH /api/staff/{staff_id}/reset-password)
# ============================================================================


async def test_admin_reset_password_success(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)
    staff.hashed_password = "$2b$12$oldhashplaceholder0000"
    await db.commit()

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/reset-password",
        json={"new_password": "NewTemp123"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert "message" in response.json()


async def test_admin_reset_password_credential_actually_changes(
    client: AsyncClient,
    db,
    admin_staff,
    admin_headers,
    department,
):
    """
    Full verification: after reset the new password verifies against the
    stored hash and the old one no longer does.
    """
    old_password = "Password123!"
    admin_staff.hashed_password = None  # placeholder; set real hash below
    from app.core.security import hash_password

    admin_staff.hashed_password = hash_password(old_password)
    await db.commit()

    new_password = "BrandNew456"

    response = await client.patch(
        f"/api/staff/{admin_staff.staff_id}/reset-password",
        json={"new_password": new_password},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    await db.refresh(admin_staff)
    assert verify_password(new_password, admin_staff.hashed_password)
    assert not verify_password(old_password, admin_staff.hashed_password)


async def test_admin_reset_password_rejects_weak_password(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/reset-password",
        json={"new_password": "weak"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_admin_reset_password_rejects_no_digit(
    client: AsyncClient,
    admin_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/reset-password",
        json={"new_password": "NoDigitsHere"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_admin_reset_password_not_found(
    client: AsyncClient,
    admin_headers,
):
    response = await client.patch(
        f"/api/staff/{uuid4()}/reset-password",
        json={"new_password": "NewTemp123"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_admin_reset_password_forbidden_for_doctor(
    client: AsyncClient,
    doctor_token_headers,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/reset-password",
        json={"new_password": "NewTemp123"},
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_admin_reset_password_unauthorized(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_staff(db, department)

    response = await client.patch(
        f"/api/staff/{staff.staff_id}/reset-password",
        json={"new_password": "NewTemp123"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# GROUP 4: AUDIT TRAIL OF ADMIN ACTIONS
# ============================================================================


async def test_admin_actions_are_audit_logged(
    client: AsyncClient,
    admin_headers,
    admin_staff,
    db,
    department,
    secondary_department,
):
    """
    Role change, transfer and password reset must leave entries in the
    audit ledger (read back through the admin audit-logs endpoint).
    """
    staff = await make_staff(db, department)

    await client.patch(
        f"/api/staff/{staff.staff_id}/role",
        json={"role": "NURSE"},
        headers=admin_headers,
    )
    await client.patch(
        f"/api/staff/{staff.staff_id}/transfer",
        json={"dept_id": str(secondary_department.dept_id)},
        headers=admin_headers,
    )
    await client.patch(
        f"/api/staff/{staff.staff_id}/reset-password",
        json={"new_password": "NewTemp123"},
        headers=admin_headers,
    )

    response = await client.get(
        f"/api/admin/audit-logs?staff_id={admin_staff.staff_id}",
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    actions = {entry["action"] for entry in response.json()}
    assert {"ROLE_CHANGED", "DEPARTMENT_TRANSFER", "PASSWORD_RESET"} <= actions
