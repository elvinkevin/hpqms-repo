"""
Regression tests for the first-login credential flows:

    POST /api/auth/login                      (setup / password-change gates)
    POST /api/auth/complete-admin-setup       (first-time administrator setup)
    POST /api/auth/complete-password-change   (staff temporary-password change)
    PATCH /api/staff/{staff_id}/reset-password (admin-issued recovery code)
"""
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from fastapi import status

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.domain.models.models import Staff, StaffRole
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


# ============================================================================
# HELPERS
# ============================================================================


async def make_pending_staff(
    db: AsyncSession,
    department,
    *,
    role: StaffRole = StaffRole.DOCTOR,
    employee_id: str | None = None,
    temp_password: str = "TempPass123!",
    admin_setup_complete: bool = True,
    requires_password_change: bool = True,
    reset_code: str | None = None,
    reset_code_expires_at: datetime | None = None,
) -> Staff:
    """
    Create a staff member in whatever pending-credential state a test needs.

    - Admin first-time setup: role=ADMIN, admin_setup_complete=False.
    - Staff temporary password: requires_password_change=True, no reset code.
    - Admin-issued recovery: reset_code set (hashed) alongside requires_password_change.
    """
    staff = Staff(
        staff_id=uuid4(),
        employee_id=employee_id or f"EMP-{uuid4().hex[:8]}",
        first_name="Pending",
        last_name="Staff",
        role=role,
        dept_id=department.dept_id,
        hashed_password=hash_password(temp_password),
        is_active=True,
        admin_setup_complete=admin_setup_complete,
        requires_password_change=requires_password_change,
        password_reset_code_hash=hash_password(reset_code) if reset_code else None,
        password_reset_code_expires_at=(
            reset_code_expires_at
            or (datetime.now(timezone.utc) + timedelta(minutes=15) if reset_code else None)
        ),
    )
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    return staff


# ============================================================================
# GROUP 1: ADMIN FIRST-TIME LOGIN GATE
# ============================================================================


async def test_first_admin_login_returns_setup_token_not_session(
    client: AsyncClient,
    db,
    department,
):
    """
    An administrator with an unfinished profile must receive a restricted
    setup token instead of access/refresh tokens.
    """
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
        employee_id="EMP-SETUP01",
    )

    response = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-SETUP01", "password": "TempPass123!"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["setup_required"] is True
    assert body["setup_token"]
    assert body["access_token"] is None
    assert body["refresh_token"] is None
    assert body["password_change_required"] is False


async def test_first_admin_login_wrong_temporary_password_rejected(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
        employee_id="EMP-SETUP02",
    )

    response = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-SETUP02", "password": "WrongPass123!"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_unfinished_admin_cannot_use_protected_endpoints(
    client: AsyncClient,
    db,
    department,
):
    """
    An access token minted for an admin who has not completed setup must be
    rejected by get_current_user (403).
    """
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
    )
    token = create_access_token(
        {
            "sub": str(staff.staff_id),
            "employee_id": staff.employee_id,
            "role": staff.role.value,
            "dept_id": str(staff.dept_id),
        }
    )

    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_unfinished_admin_cannot_refresh_session(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
    )
    refresh = create_refresh_token(str(staff.staff_id))

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# GROUP 2: COMPLETE ADMIN SETUP
# ============================================================================


async def test_complete_admin_setup_success(
    client: AsyncClient,
    db,
    department,
):
    """Full first-login journey: login -> setup -> session tokens."""
    temp_password = "TempPass123!"
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
        temp_password=temp_password,
        employee_id="EMP-SETUP03",
    )

    login_response = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-SETUP03", "password": temp_password},
    )
    body = login_response.json()
    setup_token = body["setup_token"]
    assert setup_token

    setup_response = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": setup_token,
            "first_name": "Ada",
            "last_name": "Administrator",
            "new_password": "BrandNewPass123!",
        },
    )

    assert setup_response.status_code == status.HTTP_200_OK
    setup_body = setup_response.json()
    assert setup_body["access_token"]
    assert setup_body["refresh_token"]
    assert setup_body["setup_required"] is False

    await db.refresh(staff)
    assert staff.admin_setup_complete is True
    assert staff.requires_password_change is False
    assert staff.first_name == "Ada"
    assert staff.last_name == "Administrator"
    assert verify_password("BrandNewPass123!", staff.hashed_password)
    assert not verify_password(temp_password, staff.hashed_password)

    # The new permanent password grants a normal session.
    final_login = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-SETUP03", "password": "BrandNewPass123!"},
    )
    assert final_login.status_code == status.HTTP_200_OK
    assert final_login.json()["access_token"]


async def test_complete_admin_setup_rejects_same_temporary_password(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
        temp_password="TempPass123!",
    )

    login_response = await client.post(
        "/api/auth/login",
        json={"employee_id": staff.employee_id, "password": "TempPass123!"},
    )
    setup_token = login_response.json()["setup_token"]

    response = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": setup_token,
            "first_name": "Ada",
            "last_name": "Administrator",
            "new_password": "TempPass123!",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_complete_admin_setup_rejects_replay(
    client: AsyncClient,
    db,
    department,
):
    """A second attempt with a valid setup token after completion conflicts."""
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
    )

    login_response = await client.post(
        "/api/auth/login",
        json={"employee_id": staff.employee_id, "password": "TempPass123!"},
    )
    setup_token = login_response.json()["setup_token"]

    first = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": setup_token,
            "first_name": "Ada",
            "last_name": "Administrator",
            "new_password": "BrandNewPass123!",
        },
    )
    assert first.status_code == status.HTTP_200_OK

    second = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": setup_token,
            "first_name": "Ada",
            "last_name": "Administrator",
            "new_password": "AnotherPass123!",
        },
    )

    assert second.status_code == status.HTTP_409_CONFLICT


async def test_complete_admin_setup_rejects_garbage_token(
    client: AsyncClient,
):
    response = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": "not.a.jwt",
            "first_name": "Ada",
            "last_name": "Administrator",
            "new_password": "BrandNewPass123!",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_admin_setup_token_rejected_for_non_admin(
    client: AsyncClient,
    db,
    department,
):
    """A setup token scoped to a non-ADMIN account must not be honoured."""
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.DOCTOR,
        admin_setup_complete=False,
    )

    from app.core.security import create_admin_setup_token

    setup_token = create_admin_setup_token(str(staff.staff_id))

    response = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": setup_token,
            "first_name": "Doc",
            "last_name": "Tor",
            "new_password": "BrandNewPass123!",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_complete_admin_setup_requires_strong_password(
    client: AsyncClient,
    db,
    department,
):
    """Schema validation: weak passwords never reach the service layer."""
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
    )

    login_response = await client.post(
        "/api/auth/login",
        json={"employee_id": staff.employee_id, "password": "TempPass123!"},
    )
    setup_token = login_response.json()["setup_token"]

    response = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": setup_token,
            "first_name": "Ada",
            "last_name": "Administrator",
            "new_password": "short",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================================================
# GROUP 3: STAFF TEMPORARY PASSWORD / FIRST LOGIN
# ============================================================================


async def test_staff_first_login_returns_password_change_token(
    client: AsyncClient,
    db,
    department,
):
    """
    A newly provisioned staff account must receive a restricted
    password-change token instead of session tokens.
    """
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.DOCTOR,
        employee_id="EMP-TEMP01",
    )

    response = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-TEMP01", "password": "TempPass123!"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["password_change_required"] is True
    assert body["password_change_token"]
    assert body["access_token"] is None
    assert body["refresh_token"] is None


async def test_pending_staff_blocked_from_protected_endpoints(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(db, department)
    token = create_access_token(
        {
            "sub": str(staff.staff_id),
            "employee_id": staff.employee_id,
            "role": staff.role.value,
            "dept_id": str(staff.dept_id),
        }
    )

    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_pending_staff_cannot_refresh(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(db, department)
    refresh = create_refresh_token(str(staff.staff_id))

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_complete_staff_password_change_success(
    client: AsyncClient,
    db,
    department,
):
    """Login -> password change -> permanent login works."""
    temp_password = "TempPass123!"
    new_password = "BrandNewPass456!"
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.DOCTOR,
        temp_password=temp_password,
        employee_id="EMP-TEMP02",
    )

    login_response = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-TEMP02", "password": temp_password},
    )
    change_token = login_response.json()["password_change_token"]
    assert change_token

    change_response = await client.post(
        "/api/auth/complete-password-change",
        json={"password_change_token": change_token, "new_password": new_password},
    )

    assert change_response.status_code == status.HTTP_200_OK
    body = change_response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["password_change_required"] is False

    await db.refresh(staff)
    assert staff.requires_password_change is False
    assert verify_password(new_password, staff.hashed_password)
    assert not verify_password(temp_password, staff.hashed_password)

    final_login = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-TEMP02", "password": new_password},
    )
    assert final_login.status_code == status.HTTP_200_OK
    assert final_login.json()["access_token"]


async def test_complete_staff_password_change_rejects_same_temporary_password(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.DOCTOR,
        temp_password="TempPass123!",
    )

    login_response = await client.post(
        "/api/auth/login",
        json={"employee_id": staff.employee_id, "password": "TempPass123!"},
    )
    change_token = login_response.json()["password_change_token"]

    response = await client.post(
        "/api/auth/complete-password-change",
        json={"password_change_token": change_token, "new_password": "TempPass123!"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_complete_staff_password_change_rejects_replay(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(db, department)

    login_response = await client.post(
        "/api/auth/login",
        json={"employee_id": staff.employee_id, "password": "TempPass123!"},
    )
    change_token = login_response.json()["password_change_token"]

    first = await client.post(
        "/api/auth/complete-password-change",
        json={"password_change_token": change_token, "new_password": "BrandNewPass456!"},
    )
    assert first.status_code == status.HTTP_200_OK

    second = await client.post(
        "/api/auth/complete-password-change",
        json={"password_change_token": change_token, "new_password": "AnotherPass456!"},
    )

    assert second.status_code == status.HTTP_409_CONFLICT


async def test_complete_staff_password_change_rejects_garbage_token(
    client: AsyncClient,
):
    response = await client.post(
        "/api/auth/complete-password-change",
        json={"password_change_token": "garbage.token.value", "new_password": "BrandNewPass456!"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# GROUP 4: ADMIN-INITIATED PASSWORD RESET (RECOVERY CODE JOURNEY)
# ============================================================================


async def test_login_with_recovery_code_returns_password_change_token(
    client: AsyncClient,
    db,
    department,
):
    """
    After an admin-issued reset, the recovery code is the only valid
    credential and grants a password-change token, not a session.
    """
    recovery_code = "HPQMS-1234567890"
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.NURSE,
        requires_password_change=True,
        reset_code=recovery_code,
        employee_id="EMP-RECOVER01",
    )
    # Simulate that the old password was already invalidated by the reset.
    staff.hashed_password = hash_password("irrelevant-old-password")
    await db.commit()

    response = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-RECOVER01", "password": recovery_code},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["password_change_required"] is True
    assert body["password_change_token"]
    assert body["access_token"] is None


async def test_recovery_code_is_single_use(
    client: AsyncClient,
    db,
    department,
):
    """A consumed recovery code cannot be used again."""
    recovery_code = "HPQMS-0987654321"
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.NURSE,
        reset_code=recovery_code,
        employee_id="EMP-RECOVER02",
    )
    staff.hashed_password = hash_password("irrelevant-old-password")
    await db.commit()

    first = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-RECOVER02", "password": recovery_code},
    )
    assert first.status_code == status.HTTP_200_OK

    await db.refresh(staff)
    assert staff.password_reset_code_hash is None

    second = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-RECOVER02", "password": recovery_code},
    )

    assert second.status_code == status.HTTP_401_UNAUTHORIZED


async def test_login_with_wrong_recovery_code_rejected(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.NURSE,
        reset_code="HPQMS-1111111111",
    )

    response = await client.post(
        "/api/auth/login",
        json={"employee_id": staff.employee_id, "password": "HPQMS-2222222222"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_expired_recovery_code_rejected(
    client: AsyncClient,
    db,
    department,
):
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.NURSE,
        reset_code="HPQMS-3333333333",
        reset_code_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    response = await client.post(
        "/api/auth/login",
        json={"employee_id": staff.employee_id, "password": "HPQMS-3333333333"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_full_reset_to_new_password_journey(
    client: AsyncClient,
    db,
    department,
):
    """
    End-to-end lockout recovery: admin resets -> staff logs in with the
    recovery code -> completes the password change -> signs in normally.
    """
    temp_password = "TempPass123!"
    staff = await make_pending_staff(
        db,
        department,
        role=StaffRole.NURSE,
        requires_password_change=False,
        temp_password=temp_password,
        employee_id="EMP-RECOVER03",
    )

    # 1. Admin issues the reset and receives the one-time code.
    # (Create an independent fully-provisioned admin for the reset call.)
    admin = await make_pending_staff(
        db,
        department,
        role=StaffRole.ADMIN,
        admin_setup_complete=False,
        temp_password="AdminTemp123!",
        employee_id="EMP-RECOVER04",
    )
    admin_login = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-RECOVER04", "password": "AdminTemp123!"},
    )
    admin_setup = await client.post(
        "/api/auth/complete-admin-setup",
        json={
            "setup_token": admin_login.json()["setup_token"],
            "first_name": "Root",
            "last_name": "Admin",
            "new_password": "RootAdminPass1!",
        },
    )
    admin_token = admin_setup.json()["access_token"]

    reset_response = await client.patch(
        f"/api/staff/{staff.staff_id}/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reset_response.status_code == status.HTTP_200_OK
    recovery_code = reset_response.json()["recovery_code"]
    assert re.fullmatch(r"HPQMS-\d{10}", recovery_code)

    await db.refresh(staff)
    assert staff.requires_password_change is True
    assert not verify_password(temp_password, staff.hashed_password)

    # 2. Staff signs in with the recovery code.
    code_login = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-RECOVER03", "password": recovery_code},
    )
    assert code_login.status_code == status.HTTP_200_OK
    change_token = code_login.json()["password_change_token"]
    assert change_token

    # 3. Staff sets a new permanent password.
    new_password = "FreshStart789!"
    change_response = await client.post(
        "/api/auth/complete-password-change",
        json={"password_change_token": change_token, "new_password": new_password},
    )
    assert change_response.status_code == status.HTTP_200_OK

    # 4. Normal login with the new password succeeds.
    final_login = await client.post(
        "/api/auth/login",
        json={"employee_id": "EMP-RECOVER03", "password": new_password},
    )
    assert final_login.status_code == status.HTTP_200_OK
    assert final_login.json()["access_token"]

    await db.refresh(staff)
    assert verify_password(new_password, staff.hashed_password)
    assert staff.requires_password_change is False
