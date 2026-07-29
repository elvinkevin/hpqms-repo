import pytest

from app.domain.models.models import StaffRole
from app.domain.schemas.schemas import StaffCreate
from app.domain.services.staff_service import StaffService
from fastapi import status

#------------------------------------------
# Test 1 Test successful login
#------------------------------------------
@pytest.mark.asyncio
async def test_login_success(
    client,
    auth_staff,
):

    response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": "ADM001",
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


#--------------------------------------------
# Test 2 test Unknown empoyee
#---------------------------------------------
@pytest.mark.asyncio
async def test_unknown_employee(client):

    response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": "UNKNOWN",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401

#-----------------------------------------
# Test 3 Wrong Password Login
#------------------------------------------
@pytest.mark.asyncio
async def test_wrong_password(
    client,
    auth_staff,
):

    response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": "ADM001",
            "password": "WrongPassword",
        },
    )

    assert response.status_code == 401


#------------------------------------------------
# Test 4 Test inactive Staff Login
#------------------------------------------------
@pytest.mark.asyncio
async def test_inactive_staff_cannot_login(
    client,
    auth_staff,
    db,
):

    auth_staff.is_active = False

    await db.commit()

    response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": "ADM001",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401


#----------------------------------------
# Test 5 missing password
#----------------------------------------
@pytest.mark.asyncio
async def test_missing_password(client):

    response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": "ADM001",
        },
    )

    assert response.status_code == 422


#--------------------------------------------------
# Test 6 missing employee id
#---------------------------------------------------
@pytest.mark.asyncio
async def test_missing_employee_id(client):

    response = await client.post(
        "/api/auth/login",
        json={
            "password": "Password123!",
        },
    )

    assert response.status_code == 422


#--------------------------------------------
# test 7 empty request
#---------------------------------------------
@pytest.mark.asyncio
async def test_empty_login_request(client):

    response = await client.post(
        "/api/auth/login",
        json={},
    )

    assert response.status_code == 422



# ---------------------------------------------------------
# REFRESH TOKEN TESTS
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_token_success(client, auth_staff):
    """
    Ensure a valid refresh token returns a new access token.
    """
    # 1. Login to retrieve initial tokens
    login_response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": auth_staff.employee_id,
            "password": "Password123!",
        },
    )
    assert login_response.status_code == status.HTTP_200_OK
    tokens = login_response.json()
    refresh_token = tokens["refresh_token"]

    # 2. Exchange refresh token for new access token
    refresh_response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert refresh_response.status_code == status.HTTP_200_OK
    
    body = refresh_response.json()
    assert "access_token" in body
    assert body.get("token_type") == "bearer"


@pytest.mark.asyncio
async def test_refresh_token_invalid(client):
    """
    Ensure an invalid or malformed refresh token returns 401 Unauthorized.
    """
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid.jwt.token.here"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED



# ---------------------------------------------------------
# CURRENT USER TESTS (/api/auth/me)
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_user_success(client, auth_staff, auth_headers):
    """
    Ensure an authenticated request with a valid Bearer token 
    returns the correct current staff member's profile.
    """
    response = await client.get(
        "/api/auth/me",
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["employee_id"] == auth_staff.employee_id
    assert body["first_name"] == auth_staff.first_name
    assert body["last_name"] == auth_staff.last_name


@pytest.mark.asyncio
async def test_get_current_user_missing_jwt(client):
    """
    Ensure requesting protected user data without an Authorization header 
    returns 401 Unauthorized.
    """
    response = await client.get("/api/auth/me")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_invalid_jwt(client):
    """
    Ensure requesting protected user data with a garbage/malformed token 
    returns 401 Unauthorized.
    """
    headers = {"Authorization": "Bearer invalid.token.payload"}
    response = await client.get(
        "/api/auth/me",
        headers=headers,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED



# ---------------------------------------------------------
# CHANGE PASSWORD TESTS
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_change_password_success(client, auth_staff, auth_headers):
    """
    Ensure an authenticated user can update their password and subsequently 
    login with the new credentials.
    """
    # 1. Change password
    response = await client.post(
        "/api/auth/change-password",
        headers=auth_headers,
        json={
            "current_password": "Password123!",
            "new_password": "NewSecurePassword123!",
        },
    )

    assert response.status_code == status.HTTP_200_OK

    # 2. Verify login succeeds with new password
    login_response = await client.post(
        "/api/auth/login",
        json={
            "employee_id": auth_staff.employee_id,
            "password": "NewSecurePassword123!",
        },
    )
    assert login_response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_change_password_wrong_current(client, auth_headers):
    """
    Ensure password change fails if the current password supplied is incorrect.
    """
    response = await client.post(
        "/api/auth/change-password",
        headers=auth_headers,
        json={
            "current_password": "WrongCurrentPassword123!",
            "new_password": "NewSecurePassword123!",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_change_password_weak_password(client, auth_headers):
    """
    Ensure schema or domain validations reject weak passwords.
    """
    response = await client.post(
        "/api/auth/change-password",
        headers=auth_headers,
        json={
            "current_password": "Password123!",
            "new_password": "123",  # Fails minimum complexity/length rules
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_change_password_missing_jwt(client):
    """
    Ensure unauthenticated password change attempts are rejected.
    """
    response = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "Password123!",
            "new_password": "NewSecurePassword123!",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------
# LOGOUT TESTS
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_success(client, auth_headers):
    """
    Ensure an authenticated staff member can log out successfully.
    """
    response = await client.post(
        "/api/auth/logout",
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["message"] == "Logged out successfully."


@pytest.mark.asyncio
async def test_logout_unauthenticated(client):
    """
    Ensure logging out without a Bearer token returns 401 Unauthorized.
    """
    response = await client.post("/api/auth/logout")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED