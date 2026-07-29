import re
from datetime import datetime, timezone, date
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.models import Visit, EntryType, VisitStage, DailyTokenCounter


class TokenService:
    # ── CLASS CONSTANTS ───────────────────────────────────────────────
    PREFIX_MAP = {
        EntryType.WALK_IN: "W",
        EntryType.REFERRAL: "W",
        EntryType.APPOINTMENT: "A",
        EntryType.EMERGENCY: "E",
    }

    START_OFFSETS = {
        "W": 100,
        "A": 200,
        "E": 0,
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # GENERATE TOKEN
    # ------------------------------------------------------------------
    async def generate_token(self, entry_type: EntryType) -> str:
        """
        Generates daily sequential token sequences by leveraging the DailyTokenCounter ledger.
        Ensures atomic upserts to completely prevent token collisions across concurrent kiosks.
        """
        prefix = self.PREFIX_MAP.get(entry_type, "G")
        base_offset = self.START_OFFSETS.get(prefix, 100)

        # 1. Capture today's UTC date baseline
        today_date = datetime.now(timezone.utc).date()

        # 2. Execute atomic PostgreSQL Upsert (ON CONFLICT DO UPDATE)
        stmt = (
            insert(DailyTokenCounter)
            .values(
                counter_date=today_date,
                entry_type=entry_type,
                last_number=1,
            )
            .on_conflict_do_update(
                constraint="uq_date_entry_type",
                set_={"last_number": DailyTokenCounter.last_number + 1},
            )
            .returning(DailyTokenCounter.last_number)
        )

        result = await self.db.execute(stmt)
        current_sequence = result.scalar_one()
        await self.db.flush()  # Ensures sequence is locked & visible in current transaction

        # 3. Apply offset representation rules
        formatted_number = base_offset + current_sequence

        # For E (where offset is 0), zero-pad to 3 digits (e.g. E-001) for consistency
        if prefix == "E":
            return f"{prefix}-{formatted_number:03d}"

        return f"{prefix}-{formatted_number}"

    # ------------------------------------------------------------------
    # GET VISIT BY TOKEN
    # ------------------------------------------------------------------
    async def get_visit_by_token(self, token_number: str) -> Visit:
        """
        Retrieves an ongoing visit session matching a printed token number.
        Sanitizes loose formats (e.g. 'w101', 'W 101', 'w-101') into canonical format 'W-101'.
        """
        if not token_number or not token_number.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token number cannot be empty.",
            )

        # 1. Standardize string casing and strip whitespace
        raw = token_number.strip().upper().replace(" ", "")

        # 2. Robust Regex pattern matching (Prefix Letter + Optional Hyphen + Digits)
        match = re.match(r"^([A-Z])-?(\d+)$", raw)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid token format '{token_number}'. Expected formats like 'W-101', 'W101', or 'E-001'.",
            )

        prefix, num_str = match.groups()

        # 3. Reconstruct canonical token identifier
        if prefix == "E":
            clean_token = f"{prefix}-{int(num_str):03d}"  # Normalizes 'E1' or 'E-1' to 'E-001'
        else:
            clean_token = f"{prefix}-{num_str}"

        # 4. Lookup Active Visit
        result = await self.db.execute(
            select(Visit).where(
                Visit.token_number == clean_token,
                Visit.stage == VisitStage.ACTIVE,
            )
        )
        visit = result.scalar_one_or_none()

        if not visit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active hospital visit session found matching token identifier '{clean_token}'.",
            )

        return visit