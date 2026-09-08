from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.services.auth_service import get_current_user
from app.domain.models.models import Staff, Visit
from app.domain.schemas.schemas import (
    VitalsCreate,
    VitalsRead,
    TriageAssessmentUpdate,
    VisitRead,
    CurrentUser,
)
from app.domain.services.vitals_service import VitalsService

router = APIRouter(
    tags=["Visits & Vitals & Triage"],
)


# ==============================================================================
# VITALS ENDPOINTS
# ==============================================================================

@router.post(
    "/{visit_id}/vitals",
    response_model=VitalsRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_visit_vitals(
    visit_id: UUID,
    vitals_in: VitalsCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Record new vitals for a visit encounter.

    Creates a new vitals entry associated with the current visit.
    Multiple vitals can be recorded per visit to track changes over time.

    Required: Authentication

    Args:
        visit_id: UUID of the visit
        vitals_in: Vitals data to record
        db: Database session
        current_user: Authenticated staff member

    Returns:
        VitalsRead: The recorded vitals entry

    Status Codes:
        201 Created: Vitals recorded successfully
        404 Not Found: Visit doesn't exist
        401 Unauthorized: Not authenticated
        422 Unprocessable Entity: Invalid data
    """
    vitals = await VitalsService.record_vitals(
        db=db,
        visit_id=visit_id,
        staff_id=current_user.staff_id,
        vitals_in=vitals_in,
    )

    await db.commit()
    return vitals


@router.get(
    "/{visit_id}/vitals/latest",
    response_model=Optional[VitalsRead],
)
async def get_latest_vitals(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieve the most recent vitals recorded for a visit.

    Returns the latest vitals entry based on recorded_at timestamp.

    Args:
        visit_id: UUID of the visit
        db: Database session
        current_user: Authenticated staff member

    Returns:
        VitalsRead | None: The latest vitals entry, or None if none exist

    Status Codes:
        200 OK: Latest vitals retrieved (may be null)
        401 Unauthorized: Not authenticated
        422 Unprocessable Entity: Invalid visit_id format
    """
    return await VitalsService.get_latest_vitals(db=db, visit_id=visit_id)


@router.get(
    "/{visit_id}/vitals",
    response_model=List[VitalsRead],
)
async def get_all_vitals(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieve all recorded vitals for a visit encounter.

    Returns all vitals entries for the visit, ordered by
    most recent first (reverse chronological order).

    Args:
        visit_id: UUID of the visit
        db: Database session
        current_user: Authenticated staff member

    Returns:
        List[VitalsRead]: List of vitals entries (empty if none exist)

    Status Codes:
        200 OK: Vitals retrieved (may be empty list)
        401 Unauthorized: Not authenticated
        422 Unprocessable Entity: Invalid visit_id format
    """
    vitals_list = await VitalsService.get_all_vitals(db=db, visit_id=visit_id)
    return list(vitals_list)


# ==============================================================================
# TRIAGE ASSESSMENT ENDPOINTS
# ==============================================================================

@router.patch(
    "/{visit_id}/triage-assessment",
    response_model=VisitRead,
)
async def update_triage_assessment(
    visit_id: UUID,
    assessment_in: TriageAssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Update chief complaint and triage assessment for a visit.

    Updates the triage-related fields on the Visit record.
    Supports partial updates - only provided fields are updated.

    The response includes the latest_vitals if any have been recorded,
    to provide clinical context.

    Required: Authentication

    Args:
        visit_id: UUID of the visit
        assessment_in: Triage assessment data (complaint and assessment)
        db: Database session
        current_user: Authenticated staff member

    Returns:
        VisitRead: Updated visit with latest vitals included

    Status Codes:
        200 OK: Assessment updated successfully
        404 Not Found: Visit doesn't exist
        401 Unauthorized: Not authenticated
        422 Unprocessable Entity: Invalid data
    """
    # 1. Update the clinical triage assessment on the visit.
    visit = await VitalsService.update_triage_assessment(
        db=db,
        visit_id=visit_id,
        assessment_in=assessment_in,
    )

    await db.commit()
    await db.refresh(visit)

       # 2. Hydrate latest vitals for context
    latest_vitals = await VitalsService.get_latest_vitals(db=db, visit_id=visit_id)

    # 3. Dynamically capture ALL fields from the model instance
    visit_dict = {
        **{c.name: getattr(visit, c.name) for c in visit.__table__.columns},
        "latest_vitals": latest_vitals,
    }

    # 4. Construct response payload using the unified dictionary
    visit_data = VisitRead.model_validate(visit_dict)

    return visit_data
