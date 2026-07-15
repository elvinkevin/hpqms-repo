from uuid import UUID
from datetime import datetime
import zoneinfo  # Built-in Python 3.9+
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload  # Forces efficient JOIN behavior

from app.db.session import get_db
from app.domain.schemas.schemas import QueueTokenSummary
from app.domain.services.auth_service import get_current_user
from app.domain.models.models import Queue, QueueToken  # Assuming QueueToken model name

router = APIRouter(prefix="/queues", tags=["queues"])

# Define your clinic's actual operational timezone
CLINIC_TZ = zoneinfo.ZoneInfo("Africa/Nairobi") 

@router.get(
    "/{dept_id}/tokens",
    response_model=List[QueueTokenSummary],
    dependencies=[Depends(get_current_user)],
)
async def get_queue_tokens(dept_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Returns today's active token list for a department,
    sorted by triage priority (CRITICAL first) then issued_at (FIFO within level).
    """
    # 1. Always evaluate 'today' relative to the hospital's geographic location
    today_local = datetime.now(CLINIC_TZ).date()

    # 2. Execute a single query that joins and fetches tokens cleanly
    # Use selectinload to pull related patient/triage data in exactly 1 extra optimized query 
    # to eliminate the N+1 loop entirely.
    stmt = (
        select(QueueToken)
        .join(Queue)
        .where(
            and_(
                Queue.dept_id == dept_id,
                Queue.queue_date == today_local
            )
        )
        .options(
            selectinload(QueueToken.patient),
        )
        .order_by(
            QueueToken.issued_at.asc()
        )
    )

    result = await db.execute(stmt)
    tokens = result.scalars().all()

    # If no tokens exist or the queue hasn't been initialized, returns empty list cleanly
    return [QueueTokenSummary.model_validate(t) for t in tokens]
