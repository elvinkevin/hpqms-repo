from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status

from app.db.session import get_db
from app.core.security import decode_token, verify_password, create_access_token
from app.domain.models.models import Staff, StaffRole
from app.domain.schemas.schemas import CurrentUser


class AuthService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate(self, employee_id: str, password: str) -> Staff:
        result = await self.db.execute(
            select(Staff).where(
                Staff.employee_id == employee_id,
                Staff.is_active == True,
            )
        )
        staff = result.scalar_one_or_none()

        if not staff or not verify_password(password, staff.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid employee ID or password",
            )
        return staff

    def build_token(self, staff: Staff) -> str:
        return create_access_token({
            "sub":         str(staff.staff_id),
            "employee_id": staff.employee_id,
            "role":        staff.role.value,
            "dept_id":     str(staff.dept_id),
        })


# ── FastAPI dependency — inject into any route that needs auth ────────────

async def get_current_user(
    token: str = Depends(__import__("app.core.security", fromlist=["oauth2_scheme"]).oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    payload = decode_token(token)
    staff_id = payload.get("sub")
    if not staff_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    staff = await db.get(Staff, UUID(staff_id))
    if not staff or not staff.is_active:
        raise HTTPException(status_code=401, detail="Staff account not found or inactive")

    return CurrentUser(
        staff_id=staff.staff_id,
        employee_id=staff.employee_id,
        role=staff.role,
        dept_id=staff.dept_id,
    )


def require_role(*roles: StaffRole):
    """
    Role guard factory. Usage:
        @router.post("/...", dependencies=[Depends(require_role(StaffRole.RECEPTIONIST))])
    """
    async def _guard(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role} is not permitted for this action. "
                       f"Required: {[r.value for r in roles]}",
            )
        return current_user
    return _guard
