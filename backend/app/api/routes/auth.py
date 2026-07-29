from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.schemas.schemas import (
    LoginRequest,
    TokenResponse,
    AccessTokenResponse,
    RefreshTokenRequest,
    ChangePasswordRequest,
    CurrentUser,
)
from app.domain.services.auth_service import (
    AuthService,
    get_current_user,
)
from app.domain.models.models import Staff
from app.domain.services import auth_service

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


# ---------------------------------------------------------
# REFRESH ACCESS TOKEN
# ---------------------------------------------------------

@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
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
    return await auth_service.logout()