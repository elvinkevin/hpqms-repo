# from fastapi import APIRouter, Depends
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.session import get_db
# from app.domain.schemas.schemas import LoginRequest, TokenResponse, StaffRead
# from app.domain.services.auth_service import AuthService

# router = APIRouter(prefix="/auth", tags=["auth"])


# @router.post("/login", response_model=TokenResponse)
# async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
#     """
#     Staff login. Returns a JWT valid for 8 hours.
#     Stored in memory on the frontend — never in localStorage.
#     """
#     svc = AuthService(db)
#     staff = await svc.authenticate(data.employee_id, data.password)
#     token = svc.build_token(staff)
#     return TokenResponse(access_token=token, staff=StaffRead.model_validate(staff))

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.schemas.schemas import TokenResponse, StaffRead
from app.domain.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(get_db)
):
    svc = AuthService(db)
    # form_data.username maps cleanly to your employee_id
    staff = await svc.authenticate(form_data.username, form_data.password)
    token = svc.build_token(staff)
    return TokenResponse(access_token=token, staff=StaffRead.model_validate(staff))
