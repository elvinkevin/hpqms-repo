from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.schemas.schemas import PatientCreate, PatientRead, CurrentUser
from app.domain.services.patient_service import PatientService
from app.domain.services.auth_service import get_current_user, require_role
from app.domain.services.audit_service import log_action
from app.domain.models.models import StaffRole

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post(
    "",
    response_model=PatientRead,
    status_code=201,
    dependencies=[Depends(require_role(StaffRole.RECEPTIONIST, StaffRole.ADMIN))],
)
#  CORRECT & SAFE VERSION
async def register_patient(
    data: PatientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # 1. Instantiate the service using the injected DB session
    svc = PatientService(db)

    # 2. Check for existence (safe from conflicts)
    existing = await svc.get_by_national_id(data.national_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Patient with national ID '{data.national_id}' already exists."
        )

    # 3. Process the registration 
    patient = await svc.register(data) 

    # 4. Write your audit trail record
    await log_action(
        db,
        entity_id=patient.patient_id,
        entity_type="Patient",
        action="REGISTERED",
        performed_by=current_user.staff_id,
        payload={"national_id": data.national_id},
    )
    
    # 5. Commit all changes together as one single transaction unit!
    await db.commit()
    await db.refresh(patient)
        
    return PatientRead.model_validate(patient)





@router.get(
    "/{national_id}",
    response_model=PatientRead,
    dependencies=[Depends(get_current_user)],
)
async def get_patient(national_id: str, db: AsyncSession = Depends(get_db)):
    """
    Lookup a patient by national ID.
    Used at reception desk to check if a returning patient has a record.
    """
    svc = PatientService(db)
    patient = await svc.get_by_national_id(national_id)
    if not patient:
        raise HTTPException(
            status_code=404, 
            detail=f"No patient found with national ID '{national_id}'"
        )
    return PatientRead.model_validate(patient)
