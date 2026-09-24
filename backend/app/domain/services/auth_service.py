from hmac import compare_digest
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import (
    oauth2_scheme,
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    create_admin_setup_token,
    create_password_change_token,
    decode_access_token,
    decode_refresh_token,
    decode_admin_setup_token,
    decode_password_change_token,
)
from app.core.config import settings
from app.db.session import get_db
from app.domain.models.models import Staff, StaffRole
from app.domain.schemas.schemas import (
    LoginRequest,
    TokenResponse,
    AccessTokenResponse,
    ChangePasswordRequest,
    AdminSetupCompleteRequest,
    StaffPasswordChangeCompleteRequest,
    CurrentUser,
    StationBinding,
)

KIOSK_API_KEY_NAME = "X-Kiosk-API-Key"
kiosk_key_header = APIKeyHeader(
    name=KIOSK_API_KEY_NAME,
    auto_error=False,
)

class AuthService:
    """
    Handles authentication and credential management.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @classmethod
    async def get_instance(
        cls,
        db: AsyncSession = Depends(get_db),
    ) -> "AuthService":
        return cls(db=db)

    # -----------------------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------------------

    async def get_staff(self, staff_id: UUID) -> Staff:
        """
        Retrieve a staff member by UUID.
        """
        staff = await self.db.get(Staff, staff_id)

        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found.",
            )

        return staff

    async def get_staff_by_employee_id(
        self,
        employee_id: str,
    ) -> Staff | None:
        """
        Retrieve an active staff member using employee ID.
        """
        result = await self.db.execute(
            select(Staff).where(
                Staff.employee_id == employee_id,
                Staff.is_active == True,
            ).with_for_update()
        )

        return result.scalar_one_or_none()

    def _build_access_token(self, staff: Staff) -> str:
        """
        Creates a JWT access token from a Staff object.
        """
        return create_access_token(
            {
                "sub": str(staff.staff_id),
                "employee_id": staff.employee_id,
                "role": staff.role.value,
                "dept_id": str(staff.dept_id),
            }
        )

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    async def login(
        self,
        credentials: LoginRequest,
    ) -> TokenResponse:

        staff = await self.get_staff_by_employee_id(
            credentials.employee_id
        )

        if not staff:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid employee ID or password.",
            )

        # Admin-initiated account recovery uses a distinct single-use code.
        # The old password was replaced when the code was issued.
        if staff.requires_password_change and staff.password_reset_code_hash:
            expires_at = staff.password_reset_code_expires_at
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if (
                expires_at is None
                or expires_at <= datetime.now(timezone.utc)
                or not verify_password(
                    credentials.password,
                    staff.password_reset_code_hash,
                )
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid employee ID or recovery code.",
                )

            # Consume the recovery code at login; only the short-lived
            # password-change token remains usable from this point.
            staff.password_reset_code_hash = None
            staff.password_reset_code_expires_at = None
            await self.db.commit()
            await self.db.refresh(staff)
            return TokenResponse(
                password_change_required=True,
                password_change_token=create_password_change_token(str(staff.staff_id)),
                staff=staff,
            )

        if not verify_password(credentials.password, staff.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid employee ID or password.",
            )

        if staff.role == StaffRole.ADMIN and not staff.admin_setup_complete:
            return TokenResponse(
                setup_required=True,
                setup_token=create_admin_setup_token(str(staff.staff_id)),
                staff=staff,
            )

        if staff.requires_password_change:
            return TokenResponse(
                password_change_required=True,
                password_change_token=create_password_change_token(str(staff.staff_id)),
                staff=staff,
            )

        # Desktop workstation sign-in starts a shift automatically. The
        # staff header still exposes an explicit status toggle for breaks
        # and early shift checkout.
        staff.is_on_duty = True
        await self.db.commit()
        await self.db.refresh(staff)

        return TokenResponse(
            access_token=self._build_access_token(staff),
            refresh_token=create_refresh_token(str(staff.staff_id)),
            staff=staff,
        )

    async def complete_admin_setup(
        self,
        data: AdminSetupCompleteRequest,
    ) -> TokenResponse:
        payload = decode_admin_setup_token(data.setup_token)
        staff_id = payload.get("sub")
        if not staff_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid administrator setup token.",
            )

        try:
            parsed_staff_id = UUID(staff_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid administrator setup token.",
            )

        result = await self.db.execute(
            select(Staff)
            .where(Staff.staff_id == parsed_staff_id)
            .with_for_update()
        )
        staff = result.scalar_one_or_none()
        if not staff or not staff.is_active or staff.role != StaffRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Administrator account is unavailable.",
            )
        if staff.admin_setup_complete:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Administrator setup has already been completed.",
            )
        if verify_password(data.new_password, staff.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose a password different from the temporary password.",
            )

        staff.first_name = data.first_name
        staff.last_name = data.last_name
        staff.hashed_password = hash_password(data.new_password)
        staff.admin_setup_complete = True
        staff.requires_password_change = False
        staff.password_reset_code_hash = None
        staff.password_reset_code_expires_at = None
        staff.is_on_duty = True
        await self.db.commit()
        await self.db.refresh(staff)

        return TokenResponse(
            access_token=self._build_access_token(staff),
            refresh_token=create_refresh_token(str(staff.staff_id)),
            staff=staff,
        )

    async def complete_staff_password_change(
        self,
        data: StaffPasswordChangeCompleteRequest,
    ) -> TokenResponse:
        payload = decode_password_change_token(data.password_change_token)
        staff_id = payload.get("sub")
        try:
            parsed_staff_id = UUID(staff_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password change token.",
            )

        result = await self.db.execute(
            select(Staff)
            .where(Staff.staff_id == parsed_staff_id)
            .with_for_update()
        )
        staff = result.scalar_one_or_none()
        if not staff or not staff.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Staff account is unavailable.",
            )
        if not staff.requires_password_change:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This password change has already been completed.",
            )
        if verify_password(data.new_password, staff.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose a password different from the temporary password.",
            )

        staff.hashed_password = hash_password(data.new_password)
        staff.requires_password_change = False
        staff.password_reset_code_hash = None
        staff.password_reset_code_expires_at = None
        staff.is_on_duty = True
        await self.db.commit()
        await self.db.refresh(staff)
        return TokenResponse(
            access_token=self._build_access_token(staff),
            refresh_token=create_refresh_token(str(staff.staff_id)),
            staff=staff,
        )

    # -----------------------------------------------------
    # REFRESH TOKEN
    # -----------------------------------------------------

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> AccessTokenResponse:

        payload = decode_refresh_token(refresh_token)

        staff_id = payload.get("sub")

        if not staff_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        staff = await self.get_staff(UUID(staff_id))

        if not staff.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Staff account is inactive.",
            )

        if staff.role == StaffRole.ADMIN and not staff.admin_setup_complete:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Complete administrator setup before refreshing the session.",
            )
        if staff.requires_password_change:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Change the temporary password before refreshing the session.",
            )

        return AccessTokenResponse(
            access_token=self._build_access_token(staff)
        )

    # -----------------------------------------------------
    # CHANGE PASSWORD
    # -----------------------------------------------------

    async def change_password(
        self,
        staff_id: UUID,
        data: ChangePasswordRequest,
    ) -> dict[str, str]:

        staff = await self.get_staff(staff_id)

        if not verify_password(
            data.current_password,
            staff.hashed_password,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )

        staff.hashed_password = hash_password(
            data.new_password
        )

        await self.db.flush()
        await self.db.refresh(staff)

        return {
            "message": "Password changed successfully."
        }

# -----------------------------------------------------
# LOGOUT
# -----------------------------------------------------
    async def logout(self, staff_id: UUID | None = None) -> dict[str, str]:
        """
        Signals successful logout to the client to trigger clearing of
        stored tokens (e.g., localStorage, HTTP-only cookies).
        """
        if staff_id is not None:
            staff = await self.get_staff(staff_id)
            staff.is_on_duty = False
            # Release the workstation at shift end so another staff member
            # can use it after this account signs out.
            staff.active_service_point_id = None
            await self.db.commit()

        return {
            "message": "Logged out successfully."
        }



# =====================================================
# AUTH DEPENDENCIES
# =====================================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    Validates an access token and injects the authenticated staff context.
    """

    payload = decode_access_token(token)

    staff_id = payload.get("sub")

    if not staff_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        )

    staff = await db.get(
        Staff,
        UUID(staff_id),
        options=[selectinload(Staff.active_service_point)],
    )

    if not staff or not staff.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff account not found or inactive.",
        )

    if staff.role == StaffRole.ADMIN and not staff.admin_setup_complete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete administrator setup before accessing the system.",
        )
    if staff.requires_password_change:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Change the temporary password before accessing the system.",
        )

    station = None

    if staff.active_service_point is not None:
        sp = staff.active_service_point
        station = StationBinding(
            service_point_id=sp.service_point_id,
            code=sp.code,
            label=sp.label,
            station_type=sp.station_type,
            status="CHECKED_IN",
        )

    return CurrentUser(
        staff_id=staff.staff_id,
        employee_id=staff.employee_id,
        first_name=staff.first_name,
        last_name=staff.last_name,
        role=staff.role,
        dept_id=staff.dept_id,
        station=station,
    )


def require_role(*roles: StaffRole):
    """
    RBAC dependency.

    Example:
        Depends(require_role(StaffRole.DOCTOR))
    """

    async def _guard(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:

        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{current_user.role.value}' is not permitted. "
                    f"Required roles: {[role.value for role in roles]}"
                ),
            )

        return current_user

    return _guard

def ensure_department_access(
    current_user: CurrentUser,
    dept_id: UUID,
) -> None:
    """
    Ensures that the authenticated staff member belongs
    to the requested department. Admins bypass department isolation.
    """
    # System administrators hold cross-department operational permissions
    if current_user.role == StaffRole.ADMIN:
        return

    if current_user.dept_id != dept_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this department.",
        )


async def validate_kiosk_api_key(
    api_key_header: str | None = Security(kiosk_key_header),
) -> str:
    """
    Validates that the incoming request header matches the server's
    stored secret kiosk environment variable.
    """
    expected_key = settings.KIOSK_INTERNAL_API_KEY

    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kiosk authentication backend configuration error."
        )

    if not api_key_header or not compare_digest(api_key_header, expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate Kiosk credentials."
        )

    return api_key_header
