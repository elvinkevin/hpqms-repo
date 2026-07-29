from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.models import Staff, StaffRole
from app.domain.schemas.schemas import (
    PatientCreate,
    PatientRead,
    PatientUpdate,
    EmergencyPatientCreate,
    PatientReconciliation,
)
from app.domain.services.patient_service import PatientService
from app.domain.services.auth_service import (
    get_current_user,
    require_role,
)

router = APIRouter(
    prefix="/patients",
    tags=["Patient Management"],
)


# ------------------------------------------------------------------
# CREATE FULL PATIENT PROFILE (STANDARD REGISTRATION)
# ------------------------------------------------------------------

@router.post(
    "",
    response_model=PatientRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.ADMIN,
            )
        )
    ],
)
async def create_patient(
    data: PatientCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a complete patient profile.
    Used by reception during standard first-time registration.
    """
    service = PatientService(db)
    return await service.register_standard_patient(data)


# ------------------------------------------------------------------
# EMERGENCY INTAKE (JOHN DOE REGISTRATION)
# ------------------------------------------------------------------

@router.post(
    "/emergency",
    response_model=PatientRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.TRIAGE_NURSE,
                StaffRole.DOCTOR,
                StaffRole.ADMIN,
            )
        )
    ],
)
async def create_emergency_patient(
    data: EmergencyPatientCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Rapid John Doe intake for Emergency clinical care.
    Assigns a temporary badge (e.g., TEMP-20260728-1234) and INCOMPLETE status.
    """
    service = PatientService(db)
    return await service.register_emergency_patient(data)


# ------------------------------------------------------------------
# RECONCILE EMERGENCY PATIENT IDENTITY
# ------------------------------------------------------------------

@router.patch(
    "/{patient_id}/reconcile",
    response_model=PatientRead,
    status_code=status.HTTP_200_OK,
)
async def reconcile_patient(
    patient_id: UUID,
    data: PatientReconciliation,
    db: AsyncSession = Depends(get_db),
    current_staff: Staff = Depends(
        require_role(
            StaffRole.RECEPTIONIST,
            StaffRole.ADMIN,
        )
    ),
):
    """
    Retrospectively reconciles an INCOMPLETE/temporary emergency patient record 
    with verified official demographics and transitions status to COMPLETE.
    """
    service = PatientService(db)
    return await service.reconcile_patient(
        patient_id=patient_id,
        reconcile_data=data,
        staff_id=current_staff.staff_id,
    )


# ------------------------------------------------------------------
# SEARCH PATIENTS
# ------------------------------------------------------------------

@router.get(
    "/search",
    response_model=list[PatientRead],
    dependencies=[Depends(get_current_user)],
)
async def search_patients(
    q: str = Query(
        ...,
        min_length=2,
        description="Search by patient name, phone number, national ID, or temporary badge.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Performs a flexible patient search across standard and temporary identifiers.
    """
    service = PatientService(db)
    return await service.search_patients(q)


# ------------------------------------------------------------------
# FIND PATIENT BY PHONE, NATIONAL ID, OR TEMPORARY BADGE
# ------------------------------------------------------------------

@router.get("/find/{identifier}", response_model=PatientRead)
async def find_patient(
    identifier: str,
    db: AsyncSession = Depends(get_db),
    current_staff: Staff = Depends(get_current_user),
):
    """
    Finds a single patient by exact match on National ID, Phone, or Temporary Badge.
    """
    service = PatientService(db)
    return await service.find_patient(identifier)


# ------------------------------------------------------------------
# GET PATIENT BY UUID
# ------------------------------------------------------------------

@router.get(
    "/{patient_id}",
    response_model=PatientRead,
    dependencies=[Depends(get_current_user)],
)
async def get_patient(
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves a patient profile by unique UUID.
    """
    service = PatientService(db)
    return await service.get_by_id(patient_id)


# ------------------------------------------------------------------
# UPDATE PATIENT
# ------------------------------------------------------------------

@router.patch(
    "/{patient_id}",
    response_model=PatientRead,
    dependencies=[
        Depends(
            require_role(
                StaffRole.RECEPTIONIST,
                StaffRole.ADMIN,
            )
        )
    ],
)
async def update_patient(
    patient_id: UUID,
    data: PatientUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Updates an existing patient profile's general demographics.
    """
    service = PatientService(db)
    return await service.update_patient(
        patient_id,
        data,
    )