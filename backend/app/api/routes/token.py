from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.schemas.schemas import VisitRead
from app.domain.services.auth_service import get_current_user
from app.domain.services.token_service import TokenService

router = APIRouter(
    prefix="/tokens",
    tags=["Token Management"],
)


# ==========================================================
# LOOKUP VISIT BY TOKEN
# ==========================================================

@router.get(
    "/{token_number}",
    response_model=VisitRead,
    dependencies=[Depends(get_current_user)],
)
async def get_visit_by_token(
    token_number: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Resolve a printed hospital token (e.g. W-101, A-205)
    into its active visit session.

    Used by:
    • Reception
    • Triage
    • Doctors
    • Laboratory
    • Pharmacy
    """

    service = TokenService(db)

    return await service.get_visit_by_token(token_number)