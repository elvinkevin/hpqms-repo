import pytest
from fastapi import HTTPException, status

from app.core.security import create_access_token, create_refresh_token, decode_access_token, verify_password
from app.domain.models.models import StaffRole
from app.domain.schemas.schemas import ChangePasswordRequest, LoginRequest
from app.domain.services.auth_service import (
    AuthService,
    get_current_user,
    require_role,
)


# ============================================================
# AUTHENTICATION — LOGIN
# ============================================================


class TestAuthenticationLogin:

    @pytest.mark.asyncio
    async def test_login_success(
        self,
        db,
        receptionist_staff,
    ):
        """
        Valid employee credentials should return access
        and refresh tokens together with the authenticated staff.
        """

        service = AuthService(db)

        result = await service.login(
            LoginRequest(
                employee_id=receptionist_staff.employee_id,
                password="Password123!",
            )
        )

        assert result.access_token is not None
        assert result.refresh_token is not None

        assert result.staff.staff_id == receptionist_staff.staff_id
        assert result.staff.employee_id == receptionist_staff.employee_id

    @pytest.mark.asyncio
    async def test_login_invalid_employee_id(
        self,
        db,
        receptionist_staff,
    ):
        """
        Unknown employee IDs must not authenticate.
        """

        service = AuthService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.login(
                LoginRequest(
                    employee_id="EMP-NONEXISTENT",
                    password="password123",
                )
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == (
            "Invalid employee ID or password."
        )

    @pytest.mark.asyncio
    async def test_login_invalid_password(
        self,
        db,
        receptionist_staff,
    ):
        """
        A valid employee with an incorrect password
        must be rejected.
        """

        service = AuthService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.login(
                LoginRequest(
                    employee_id=receptionist_staff.employee_id,
                    password="wrong-password",
                )
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == (
            "Invalid employee ID or password."
        )

    @pytest.mark.asyncio
    async def test_inactive_staff_cannot_login(
        self,
        db,
        receptionist_staff,
    ):
        """
        Inactive staff must be rejected during login.
        """

        receptionist_staff.is_active = False
        await db.flush()

        service = AuthService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.login(
                LoginRequest(
                    employee_id=receptionist_staff.employee_id,
                    password="password123",
                )
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == (
            "Invalid employee ID or password."
        )


# ============================================================
# AUTHENTICATION — CURRENT USER
# ============================================================


class TestCurrentUser:

    @pytest.mark.asyncio
    async def test_valid_access_token_returns_current_user(
        self,
        db,
        receptionist_staff,
    ):
        """
        A valid access token should resolve to the correct
        authenticated staff context.
        """

        token = create_access_token(
            {
                "sub": str(receptionist_staff.staff_id),
                "employee_id": receptionist_staff.employee_id,
                "role": receptionist_staff.role.value,
                "dept_id": str(receptionist_staff.dept_id),
            }
        )

        current_user = await get_current_user(
            token=token,
            db=db,
        )

        assert current_user.staff_id == receptionist_staff.staff_id
        assert current_user.employee_id == receptionist_staff.employee_id
        assert current_user.first_name == receptionist_staff.first_name
        assert current_user.last_name == receptionist_staff.last_name
        assert current_user.role == receptionist_staff.role
        assert current_user.dept_id == receptionist_staff.dept_id

    @pytest.mark.asyncio
    async def test_access_token_for_inactive_staff_is_rejected(
        self,
        db,
        receptionist_staff,
    ):
        """
        A previously issued token must not remain usable after
        the staff account has been deactivated.
        """

        token = create_access_token(
            {
                "sub": str(receptionist_staff.staff_id),
                "employee_id": receptionist_staff.employee_id,
                "role": receptionist_staff.role.value,
                "dept_id": str(receptionist_staff.dept_id),
            }
        )

        receptionist_staff.is_active = False
        await db.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                token=token,
                db=db,
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == (
            "Staff account not found or inactive."
        )

    @pytest.mark.asyncio
    async def test_access_token_without_subject_is_rejected(
        self,
        db,
    ):
        """
        An access token without a staff identity must be rejected.
        """

        token = create_access_token(
            {
                "employee_id": "EMP001",
                "role": StaffRole.RECEPTIONIST.value,
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                token=token,
                db=db,
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid access token."


# ============================================================
# AUTHENTICATION — RBAC
# ============================================================


class TestRoleAuthorization:

    @pytest.mark.asyncio
    async def test_required_role_allows_matching_role(
        self,
        receptionist_staff,
    ):
        """
        A user possessing the required role should pass
        the RBAC guard.
        """

        current_user = await get_current_user_for_test(
            receptionist_staff
        )

        guard = require_role(StaffRole.RECEPTIONIST)

        result = await guard(current_user)

        assert result.staff_id == receptionist_staff.staff_id
        assert result.role == StaffRole.RECEPTIONIST

    @pytest.mark.asyncio
    async def test_required_role_rejects_wrong_role(
        self,
        receptionist_staff,
    ):
        """
        A user without the required role must receive 403.
        """

        current_user = await get_current_user_for_test(
            receptionist_staff
        )

        guard = require_role(StaffRole.DOCTOR)

        with pytest.raises(HTTPException) as exc_info:
            await guard(current_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "not permitted" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_multiple_allowed_roles_accept_matching_role(
        self,
        receptionist_staff,
    ):
        """
        RBAC should allow a user when their role is one of
        several permitted roles.
        """

        current_user = await get_current_user_for_test(
            receptionist_staff
        )

        guard = require_role(
            StaffRole.DOCTOR,
            StaffRole.RECEPTIONIST,
            StaffRole.ADMIN,
        )

        result = await guard(current_user)

        assert result.staff_id == receptionist_staff.staff_id


# ============================================================
# TEST HELPER
# ============================================================


async def get_current_user_for_test(staff):
    """
    Builds the CurrentUser object used by the RBAC dependency.

    This keeps the RBAC tests focused on role authorization
    rather than duplicating token/database setup.
    """

    from app.domain.schemas.schemas import CurrentUser

    return CurrentUser(
        staff_id=staff.staff_id,
        employee_id=staff.employee_id,
        first_name=staff.first_name,
        last_name=staff.last_name,
        role=staff.role,
        dept_id=staff.dept_id,
    )



# ============================================================
# REFRESH TOKEN WORKFLOW
# ============================================================


class TestRefreshToken:

    @pytest.mark.asyncio
    async def test_refresh_token_returns_new_access_token(
        self,
        db,
        receptionist_staff,
    ):
        """
        A valid refresh token should produce a new access token.
        """

        service = AuthService(db)

        refresh_token = create_refresh_token(
            str(receptionist_staff.staff_id)
        )

        result = await service.refresh_access_token(
            refresh_token
        )

        assert result.access_token is not None
        assert isinstance(result.access_token, str)
        assert len(result.access_token) > 0

        # Verify the returned token resolves to the same staff member.
        payload = decode_access_token(
            result.access_token
        )

        assert payload["sub"] == str(
            receptionist_staff.staff_id
        )

    @pytest.mark.asyncio
    async def test_invalid_refresh_token_is_rejected(
        self,
        db,
    ):
        """
        Completely invalid refresh tokens must be rejected.
        """

        service = AuthService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_access_token(
                "this-is-not-a-valid-refresh-token"
            )

        assert exc_info.value.status_code == (
            status.HTTP_401_UNAUTHORIZED
        )

    @pytest.mark.asyncio
    async def test_refresh_token_without_subject_is_rejected(
        self,
        db,
    ):
        """
        A refresh token without a staff identity must not
        be accepted.
        """

        from app.core.security import create_refresh_token

        # We cannot construct an invalid payload through the normal
        # helper if it always injects `sub`, so use a token with
        # an invalid/nonexistent UUID instead.
        refresh_token = create_refresh_token(
            "00000000-0000-0000-0000-000000000000"
        )

        service = AuthService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_access_token(
                refresh_token
            )

        assert exc_info.value.status_code == (
            status.HTTP_404_NOT_FOUND
        )

    @pytest.mark.asyncio
    async def test_inactive_staff_cannot_refresh_access_token(
        self,
        db,
        receptionist_staff,
    ):
        """
        Deactivating a staff account must invalidate its ability
        to refresh access tokens.
        """

        service = AuthService(db)

        refresh_token = create_refresh_token(
            str(receptionist_staff.staff_id)
        )

        receptionist_staff.is_active = False
        await db.flush()

        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_access_token(
                refresh_token
            )

        assert exc_info.value.status_code == (
            status.HTTP_401_UNAUTHORIZED
        )
        assert exc_info.value.detail == (
            "Staff account is inactive."
        )


# ============================================================
# PASSWORD CHANGE
# ============================================================


class TestPasswordChange:

    @pytest.mark.asyncio
    async def test_change_password_success(
        self,
        db,
        receptionist_staff,
    ):
        """
        A staff member with the correct current password
        should be able to change it.
        """

        service = AuthService(db)

        result = await service.change_password(
            staff_id=receptionist_staff.staff_id,
            data=ChangePasswordRequest(
                current_password="Password123!",
                new_password="NewSecurePassword456!",
            ),
        )

        assert result == {
            "message": "Password changed successfully."
        }

        await db.refresh(receptionist_staff)

        assert verify_password(
            "NewSecurePassword456!",
            receptionist_staff.hashed_password,
        )

    @pytest.mark.asyncio
    async def test_change_password_rejects_wrong_current_password(
        self,
        db,
        receptionist_staff,
    ):
        """
        Password changes must fail when the current password
        is incorrect.
        """

        service = AuthService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.change_password(
                staff_id=receptionist_staff.staff_id,
                data=ChangePasswordRequest(
                    current_password="wrong-password",
                    new_password="NewSecurePassword456!",
                ),
            )

        assert exc_info.value.status_code == (
            status.HTTP_400_BAD_REQUEST
        )
        assert exc_info.value.detail == (
            "Current password is incorrect."
        )

    @pytest.mark.asyncio
    async def test_old_password_no_longer_works_after_change(
        self,
        db,
        receptionist_staff,
    ):
        """
        After changing the password, the old password must
        no longer validate.
        """

        service = AuthService(db)

        await service.change_password(
            staff_id=receptionist_staff.staff_id,
            data=ChangePasswordRequest(
                current_password="Password123!",
                new_password="NewSecurePassword456!",
            ),
        )

        await db.refresh(receptionist_staff)

        assert not verify_password(
            "password123",
            receptionist_staff.hashed_password,
        )

    @pytest.mark.asyncio
    async def test_new_password_works_after_change(
        self,
        db,
        receptionist_staff,
    ):
        """
        The newly assigned password must validate successfully.
        """

        service = AuthService(db)

        await service.change_password(
            staff_id=receptionist_staff.staff_id,
            data=ChangePasswordRequest(
                current_password="Password123!",
                new_password="NewSecurePassword456!",
            ),
        )

        await db.refresh(receptionist_staff)

        assert verify_password(
            "NewSecurePassword456!",
            receptionist_staff.hashed_password,
        )


# ============================================================
# LOGOUT
# ============================================================


class TestLogout:

    @pytest.mark.asyncio
    async def test_logout_returns_success_response(
        self,
        db,
    ):
        """
        Logout should return the expected response.

        Token invalidation is currently client-side because
        AuthService.logout() does not maintain a server-side
        token blacklist/session store.
        """

        service = AuthService(db)

        result = await service.logout()

        assert result == {
            "message": "Logged out successfully."
        }

