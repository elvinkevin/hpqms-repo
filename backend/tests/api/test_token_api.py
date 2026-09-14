import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient

# ============================================================================
# GROUP 1: LOOKUP VISIT BY TOKEN (GET /api/tokens/{token_number})
# ============================================================================


async def test_get_visit_by_token_success(
    client: AsyncClient,
    receptionist_token_headers,
    active_visit,
):
    """
    GET /api/tokens/{token_number}
    Successfully retrieves a visit profile via a valid token number.
    """
    response = await client.get(
        f"/api/tokens/{active_visit.token_number}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert data["visit_id"] == str(active_visit.visit_id)
    assert data["token_number"] == active_visit.token_number


async def test_get_visit_by_token_not_found(
    client: AsyncClient,
    receptionist_token_headers,
):
    """
    Well-formatted but non-existent token number returns 404 Not Found.
    """
    response = await client.get(
        "/api/tokens/W-99999",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_get_visit_by_invalid_token_format(
    client: AsyncClient,
    receptionist_token_headers,
):
    """
    Invalid token format triggers service-level regex validation and returns 400 Bad Request.
    """
    response = await client.get(
        "/api/tokens/INVALID_TOKEN_FORMAT",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


async def test_get_visit_by_lowercase_token(
    client: AsyncClient,
    receptionist_token_headers,
    active_visit,
):
    """
    Service normalizes lowercase token string inputs to uppercase and retrieves the visit profile (200 OK).
    """
    response = await client.get(
        f"/api/tokens/{active_visit.token_number.lower()}",
        headers=receptionist_token_headers,
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["visit_id"] == str(active_visit.visit_id)


async def test_get_visit_by_token_unauthorized(
    client: AsyncClient,
    active_visit,
):
    """
    Unauthenticated caller gets 401 Unauthorized.
    """
    response = await client.get(
        f"/api/tokens/{active_visit.token_number}",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_visit_by_token_inactive_staff(
    client: AsyncClient,
    db,
    doctor_token_headers,
    doctor_staff,
    active_visit,
):
    """
    Deactivated staff tokens are rejected with 401 Unauthorized.
    Deactivates doctor_staff, which directly corresponds to doctor_token_headers.
    """
    doctor_staff.is_active = False
    await db.commit()

    response = await client.get(
        f"/api/tokens/{active_visit.token_number}",
        headers=doctor_token_headers,
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_get_visit_by_token_schema(
    client: AsyncClient,
    receptionist_token_headers,
    active_visit,
):
    """
    Verifies output contract contains essential visit schema keys.
    """
    response = await client.get(
        f"/api/tokens/{active_visit.token_number}",
        headers=receptionist_token_headers,
    )


    
    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    expected_fields = {
        "visit_id",
        "patient_id",
        "token_number",
        "entry_type",
        "visit_reason",
        "stage",
    }

    assert expected_fields.issubset(data.keys())