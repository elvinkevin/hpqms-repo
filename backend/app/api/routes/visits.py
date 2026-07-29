from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.models import StaffRole
from app.domain.schemas.schemas import (
    VisitCreate,
    VisitRead,
)
from app.domain.services.visit_service import VisitService
from app.domain.services.auth_service import (
    get_current_user,
    require_role,
)

router = APIRouter(
    prefix="/visits",
    tags=["Visit Management"],
)


# ==========================================================
# CREATE VISIT
# ==========================================================

@router.post(
    "",
    response_model=VisitRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_visit(
    data: VisitCreate,
    db: AsyncSession = Depends(get_db),
):

    service = VisitService(db)
    visit = await service.start_visit(data)

    await db.commit()

    return visit


# ==========================================================
# GET VISIT
# ==========================================================

@router.get(
    "/{visit_id}",
    response_model=VisitRead,
    dependencies=[Depends(get_current_user)],
)
async def get_visit(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = VisitService(db)

    return await service.get_visit(visit_id)


# ==========================================================
# ACTIVE VISIT
# ==========================================================

@router.get(
    "/patient/{patient_id}/active",
    response_model=VisitRead,
    dependencies=[Depends(get_current_user)],
)
async def get_active_visit(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = VisitService(db)

    visit = await service.get_active_visit(patient_id)

    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active visit found.",
        )

    return visit


# ==========================================================
# COMPLETE VISIT
# ==========================================================

@router.patch(
    "/{visit_id}/complete",
    response_model=VisitRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.DOCTOR,
                StaffRole.ADMIN,
            )
        )
    ],
)
async def complete_visit(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = VisitService(db)

    visit = await service.complete_visit(visit_id)

    await db.commit()

    return visit


# ==========================================================
# CANCEL VISIT
# ==========================================================

@router.patch(
    "/{visit_id}/cancel",
    response_model=VisitRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.ADMIN,
            )
        )
    ],
)
async def cancel_visit(
    visit_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    service = VisitService(db)

    visit = await service.cancel_visit(visit_id)

    await db.commit()

    return visit