from datetime import date, timedelta
from unittest.mock import patch
from fastapi import HTTPException
import pytest

from app.domain.models.models import (
    DailyTokenCounter,
    EntryType,
    Patient,
    Visit,
    VisitStage,
)
from app.domain.services.token_service import TokenService


# ------------------------------------------------------------------------------
# Token Service Fixture
# ------------------------------------------------------------------------------
@pytest.fixture
async def token_service(db):
    """Provides a fresh TokenService instance bound to the active test database session."""
    return TokenService(db)


# ------------------------------------------------------------------------------
# Active Visit Fixture for Token Lookups
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Active Visit Fixture with Patient
# ------------------------------------------------------------------------------
@pytest.fixture
async def active_visit(db):
    """Creates a Patient and an active Visit record bound to that patient."""
    # 1. Create and persist required Patient parent entity
    patient = Patient(
        first_name="John",
        last_name="Doe",
        phone="+254700000000",
    )
    db.add(patient)
    await db.flush()  # Populates patient.patient_id

    # 2. Create Visit bound to patient
    visit = Visit(
        patient_id=patient.patient_id,  # Set mandatory Foreign Key
        token_number="W-101",
        stage=VisitStage.ACTIVE,
        entry_type=EntryType.WALK_IN,
    )
    db.add(visit)
    await db.flush()
    await db.refresh(visit)

    return visit
# ------------------------------------------------------------------------------
# Test 1 — Generate First Walk-In Token
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_walkin_token(token_service):
    """Verifies that the initial walk-in entry generates starting token 'W-101'."""
    token = await token_service.generate_token(EntryType.WALK_IN)

    assert token == "W-101"


# ------------------------------------------------------------------------------
# Test 2 — Increment Walk-In Counter
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_increment_walkin_counter(token_service):
    """Ensures sequential walk-in tokens increment cleanly (e.g., W-101 to W-102)."""
    first = await token_service.generate_token(EntryType.WALK_IN)
    second = await token_service.generate_token(EntryType.WALK_IN)

    assert first == "W-101"
    assert second == "W-102"


# ------------------------------------------------------------------------------
# Test 3 — Generate First Appointment Token
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_appointment_counter(token_service):
    """Verifies that the initial scheduled appointment entry generates 'A-201'."""
    token = await token_service.generate_token(EntryType.APPOINTMENT)

    assert token == "A-201"


# ------------------------------------------------------------------------------
# Test 4 — Generate First Emergency Token
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_emergency_counter(token_service):
    """Verifies that the initial emergency entry generates high-priority token 'E-001'."""
    token = await token_service.generate_token(EntryType.EMERGENCY)

    assert token == "E-001"


# ------------------------------------------------------------------------------
# Test 5 — Independent Counter Sequences
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counters_are_independent(token_service):
    """
    Ensures each entry type (WALK_IN, APPOINTMENT, EMERGENCY) maintains its own
    isolated sequence counter without interfering with others.
    """
    walk = await token_service.generate_token(EntryType.WALK_IN)
    appointment = await token_service.generate_token(EntryType.APPOINTMENT)
    emergency = await token_service.generate_token(EntryType.EMERGENCY)

    assert walk == "W-101"
    assert appointment == "A-201"
    assert emergency == "E-001"


# ------------------------------------------------------------------------------
# Test 6 — Multiple Sequential Walk-In Increments
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_walkin_counter_multiple_increments(token_service):
    """Validates that rapid consecutive walk-in token requests generate an unbroken sequence."""
    tokens = []

    for _ in range(5):
        tokens.append(await token_service.generate_token(EntryType.WALK_IN))

    assert tokens == [
        "W-101",
        "W-102",
        "W-103",
        "W-104",
        "W-105",
    ]


# ------------------------------------------------------------------------------
# Test 7 — Appointment Sequence Isolation from Walk-Ins
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_appointment_counter_independent(token_service):
    """Confirms generating a walk-in token prior to an appointment does not alter appointment offsets."""
    await token_service.generate_token(EntryType.WALK_IN)

    appointment = await token_service.generate_token(EntryType.APPOINTMENT)

    assert appointment == "A-201"


# ------------------------------------------------------------------------------
# Test 8 — Emergency Token Zero-Padding Sequence
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_emergency_zero_padding(token_service):
    """Ensures emergency tokens correctly increment while preserving 3-digit zero-padding."""
    first = await token_service.generate_token(EntryType.EMERGENCY)
    second = await token_service.generate_token(EntryType.EMERGENCY)

    assert first == "E-001"
    assert second == "E-002"


# ------------------------------------------------------------------------------
# Test 9 — Lookup Active Visit by Exact Token
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_visit_by_token(db, active_visit):
    """Verifies successful retrieval of an active visit using a canonical token string."""
    service = TokenService(db)

    visit = await service.get_visit_by_token(active_visit.token_number)

    assert visit.visit_id == active_visit.visit_id


# ------------------------------------------------------------------------------
# Test 10 — Case-Insensitive Token Lookup
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_token_lookup_is_case_insensitive(db, active_visit):
    """Ensures lowercase token inputs (e.g., 'w-101') are normalized and matched accurately."""
    service = TokenService(db)

    visit = await service.get_visit_by_token(active_visit.token_number.lower())

    assert visit.visit_id == active_visit.visit_id


# ------------------------------------------------------------------------------
# Test 11 — Hyphenless Token Sanitization Lookup
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lookup_without_hyphen(db, active_visit):
    """Validates that user keypad inputs lacking hyphens (e.g., 'W101') are correctly parsed."""
    service = TokenService(db)

    visit = await service.get_visit_by_token(
        active_visit.token_number.replace("-", "")
    )

    assert visit.visit_id == active_visit.visit_id


# ------------------------------------------------------------------------------
# Test 12 — Reject Invalid Token Formats
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_token_format(db):
    """Verifies that non-standard or corrupt token strings raise an HTTP 400 Bad Request."""
    service = TokenService(db)

    with pytest.raises(HTTPException) as exc:
        await service.get_visit_by_token("ABCXYZ")

    assert exc.value.status_code == 400


# ------------------------------------------------------------------------------
# Test 13 — Handle Non-Existent Active Tokens
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unknown_token_returns_404(db):
    """Ensures searching for a validly formatted token with no matching active visit raises HTTP 404."""
    service = TokenService(db)

    with pytest.raises(HTTPException) as exc:
        await service.get_visit_by_token("W-999")

    assert exc.value.status_code == 404