from hmac import compare_digest
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    oauth2_scheme,
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.core.config import settings
from app.db.session import get_db
from app.domain.models.models import Staff, StaffRole
from app.domain.schemas.schemas import (
    LoginRequest,
    TokenResponse,
    AccessTokenResponse,
    ChangePasswordRequest,
    CurrentUser,
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
            )
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

        if not staff or not verify_password(
            credentials.password,
            staff.hashed_password,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid employee ID or password.",
            )

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
    async def logout(self) -> dict[str, str]:
        """
        Signals successful logout to the client to trigger clearing of 
        stored tokens (e.g., localStorage, HTTP-only cookies).
        """
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

    staff = await db.get(Staff, UUID(staff_id))

    if not staff or not staff.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff account not found or inactive.",
        )

    return CurrentUser(
        staff_id=staff.staff_id,
        employee_id=staff.employee_id,
        first_name=staff.first_name,
        last_name=staff.last_name,
        role=staff.role,
        dept_id=staff.dept_id,
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
