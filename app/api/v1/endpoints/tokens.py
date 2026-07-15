from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Final

from app.db.session import get_db
from app.domain.schemas.schemas import (
    TokenIssueRequest, QueueTokenRead, TokenStatusUpdate, CurrentUser
)
from app.domain.services.queue_service import QueueService
from app.domain.services.auth_service import get_current_user, require_role
from app.domain.services.audit_service import log_action
from app.domain.models.models import StaffRole, TokenStatus

router = APIRouter(prefix="/tokens", tags=["tokens"])

# Security Matrix: Map target states to the exact roles authorized to set them
ROLE_STATE_PERMISSIONS: Final = {
    TokenStatus.WAITING:    frozenset({StaffRole.RECEPTIONIST, StaffRole.TRIAGE_NURSE, StaffRole.CHARGE_NURSE, StaffRole.ADMIN}),
    TokenStatus.IN_TRIAGE:  frozenset({StaffRole.TRIAGE_NURSE, StaffRole.ADMIN}),
    TokenStatus.ESCALATED:  frozenset({StaffRole.TRIAGE_NURSE, StaffRole.CHARGE_NURSE, StaffRole.ADMIN}),
    TokenStatus.CALLED:     frozenset({StaffRole.DOCTOR, StaffRole.ADMIN}),
    TokenStatus.IN_CONSULT: frozenset({StaffRole.DOCTOR, StaffRole.ADMIN}),
    TokenStatus.COMPLETED:  frozenset({StaffRole.DOCTOR, StaffRole.ADMIN}),
    TokenStatus.TRANSFERRED:frozenset({StaffRole.DOCTOR, StaffRole.ADMIN}),
    TokenStatus.CANCELLED:  frozenset({StaffRole.RECEPTIONIST, StaffRole.TRIAGE_NURSE, StaffRole.CHARGE_NURSE, StaffRole.DOCTOR, StaffRole.ADMIN}),
}

@router.post(
    "",
    response_model=QueueTokenRead,
    status_code=201,
    dependencies=[Depends(require_role(StaffRole.RECEPTIONIST, StaffRole.ADMIN))],
)
async def issue_token(
    data: TokenIssueRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Issue a walk-in queue token for a patient.
    """
    svc = QueueService(db)

    # 1. Process the generation sequentially instead of opening a nested transaction block
    token = await svc.issue_token(data.patient_id, data.dept_id, data.notes)

    # 2. Log the action within the exact same session execution path
    await log_action(
        db,
        entity_id=token.token_id,
        entity_type="QueueToken",
        action="ISSUED",
        performed_by=current_user.staff_id,
        payload={
            "token_number": token.token_number,
            "patient_id":   str(data.patient_id),
            "dept_id":      str(data.dept_id),
        },
    )
    
    # 3. Explicitly commit both operations as one single atomic unit of work
    await db.commit()
    await db.refresh(token, attribute_names=["patient"])

    return QueueTokenRead.model_validate(token)


@router.patch(
    "/{token_id}/status",
    response_model=QueueTokenRead,
    dependencies=[Depends(get_current_user)],
)
async def update_token_status(
    token_id: UUID,
    data: TokenStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Transition a token's status. 
    Enforces BOTH legal state-machine logic AND clinical role access control.
    """
    # 1. Enforce Role-to-State Medical Security Matrix
    allowed_roles = ROLE_STATE_PERMISSIONS.get(data.status, set())
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role '{current_user.role.value}' is not authorized to transition tokens to '{data.status.value}'"
        )

    svc = QueueService(db)

    # 2. Execute state-machine transition sequentially without nested context blocks
    token = await svc.update_token_status(token_id, data.status, data.notes)

    # 3. Log the status mutation
    await log_action(
        db,
        entity_id=token_id,
        entity_type="QueueToken",
        action=f"STATUS_{data.status.value}",
        performed_by=current_user.staff_id,
        payload={"new_status": data.status.value, "notes": data.notes},
    )
    
    # 4. Save and persist status updates securely
    await db.commit()
    await db.refresh(token, attribute_names=["patient"])

    return QueueTokenRead.model_validate(token)


@router.get(
    "/{token_id}/wait",
    dependencies=[Depends(get_current_user)],
)
async def get_wait_time(token_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Returns estimated wait time in minutes for a given token.
    """
    svc = QueueService(db)
    minutes = await svc.get_estimated_wait(token_id)
    return {"token_id": str(token_id), "estimated_wait_minutes": minutes}
