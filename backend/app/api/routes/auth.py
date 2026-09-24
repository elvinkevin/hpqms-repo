from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import rate_limit_auth_dependency
from app.db.session import get_db
from app.domain.schemas.schemas import (
    LoginRequest,
    TokenResponse,
    AccessTokenResponse,
    RefreshTokenRequest,
    ChangePasswordRequest,
    AdminSetupCompleteRequest,
    StaffPasswordChangeCompleteRequest,
    CurrentUser,
    StationBinding,
    StaffCheckInRequest,
)
from app.domain.services.auth_service import (
    AuthService,
    get_current_user,
)
from app.domain.models.models import Staff
from app.domain.services import auth_service
from app.domain.services.service_points_service import ServicePointService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth_dependency)],
)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate a staff member and return a new
    access token together with a refresh token.
    """

    auth_service = AuthService(db)

    return await auth_service.login(credentials)


@router.post(
    "/complete-admin-setup",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth_dependency)],
)
async def complete_admin_setup(
    data: AdminSetupCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Finalize the first administrator profile using its restricted setup token."""
    return await AuthService(db).complete_admin_setup(data)


@router.post(
    "/complete-password-change",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth_dependency)],
)
async def complete_staff_password_change(
    data: StaffPasswordChangeCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Replace a temporary staff password using its restricted login token."""
    return await AuthService(db).complete_staff_password_change(data)


# ---------------------------------------------------------
# REFRESH ACCESS TOKEN
# ---------------------------------------------------------

@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth_dependency)],
)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access token.
    """

    auth_service = AuthService(db)

    return await auth_service.refresh_access_token(
        payload.refresh_token
    )


# ---------------------------------------------------------
# CURRENT USER
# ---------------------------------------------------------

@router.get(
    "/me",
    response_model=CurrentUser,
)
async def get_logged_in_user(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Returns the authenticated staff member.
    """

    return current_user


# ---------------------------------------------------------
# STATION GATE (bind / unbind service point)
# ---------------------------------------------------------

@router.get(
    "/me/station",
    response_model=Optional[StationBinding],
)
async def get_my_station(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Station binding for the current staff member.

    Returns null when unbound — the signal for the UI to show
    the station gate interstitial.
    """
    staff = await db.get(Staff, current_user.staff_id)

    if staff is None or staff.active_service_point_id is None:
        return None

    sp = await ServicePointService.get_service_point(
        db, staff.active_service_point_id
    )

    return StationBinding(
        service_point_id=sp.service_point_id,
        code=sp.code,
        label=sp.label,
        station_type=sp.station_type,
        status="CHECKED_IN",
    )


@router.post(
    "/me/station/bind",
    response_model=StationBinding,
)
async def bind_my_station(
    payload: StaffCheckInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Bind the current staff member to a service point
    (station gate submission / mid-day switch).

    Delegates to the same service layer as the check-in endpoint,
    so department and occupancy rules are enforced identically.
    """
    staff = await db.get(Staff, current_user.staff_id)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff record not found.",
        )

    updated = await ServicePointService.check_in_staff(
        db, staff, payload.service_point_id
    )

    sp = await ServicePointService.get_service_point(
        db, updated.active_service_point_id
    )

    return StationBinding(
        service_point_id=sp.service_point_id,
        code=sp.code,
        label=sp.label,
        station_type=sp.station_type,
        status="CHECKED_IN",
    )


@router.post(
    "/me/station/unbind",
    response_model=dict,
)
async def unbind_my_station(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Release the current staff member's station binding.
    """
    staff = await db.get(Staff, current_user.staff_id)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff record not found.",
        )

    await ServicePointService.check_out_staff(db, staff)

    return {"status": "UNBOUND"}


# ---------------------------------------------------------
# CHANGE PASSWORD
# ---------------------------------------------------------

@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
)
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Allows an authenticated staff member
    to change their password.
    """

    auth_service = AuthService(db)

    result = await auth_service.change_password(
        current_user.staff_id,
        data,
    )

    await db.commit()

    return result


# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    current_staff: CurrentUser = Depends(get_current_user),
    auth_service: AuthService = Depends(AuthService.get_instance),
) -> dict[str, str]:
    """
    Endpoint to gracefully log out the current staff member.
    """
    return await auth_service.logout(current_staff.staff_id)
