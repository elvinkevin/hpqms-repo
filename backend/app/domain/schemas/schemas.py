from datetime import date, datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, Field
from sqlalchemy import Integer
from app.domain.models.models import (
    StaffRole, DeptType, EntryType, VisitStage, 
    QueueEntryStatus, QueuePriority, RegistrationStatus
)

# ── Base Configuration Mixin ──────────────────────────────────────────────

class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# ── KIOSK TOUCHSCREEN PAYLOADS ────────────────────────────────────────────

class KioskCheckInRequest(BaseModel):
    """
    Polymorphic payload used exclusively by the kiosk terminal touchscreen.
    Accepts either a National ID or a Phone Number as a single string field.
    """
    identifier: str = Field(..., description="Enter National ID or Phone Number")

    @field_validator("identifier")
    @classmethod
    def clean_identifier(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Identifier input must be at least 5 characters long")
        return v

# ── PATIENT SCHEMAS ───────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    """Used for full registration by staff via the Admin/Reception dashboard."""
    national_id: Optional[str] = None
    first_name: str
    last_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("national_id")
    @classmethod
    def validate_national_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) < 6:
                raise ValueError("national_id must be at least 6 characters")
        return v

class PatientRead(ORMBase):
    patient_id: UUID
    national_id: Optional[str] = None
    temporary_identifier: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    estimated_age: Optional[int] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None  
    phone: Optional[str] = None
    email: Optional[str] = None
    registration_status: str
    reconciled_at: Optional[datetime] = None
    reconciled_by: Optional[UUID] = None
    created_at: datetime

class PatientSummary(ORMBase):
    """Lightweight version embedded inside token/queue responses."""
    patient_id: UUID
    national_id: Optional[str]      
    first_name: Optional[str]       
    last_name: Optional[str]        
    phone: Optional[str]

class PatientUpdate(BaseModel):
    """Used by the receptionist to complete registration details or edit old patients."""
    national_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class EmergencyPatientCreate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    gender: Optional[str] = None
    estimated_age: int | None = None
    date_of_birth: date | None = None
    phone: str | None = None
    national_id: str | None = None


class PatientReconciliation(BaseModel):
    first_name: str
    last_name: str
    national_id: str
    phone: str
    date_of_birth: date
    email: EmailStr | None = None
    blood_type: str | None = None
    allergies: str | None = None

class EmergencyPatientRead(BaseModel):
    patient_id: UUID
    temporary_identifier: str
    registration_status: RegistrationStatus
    first_name: str | None
    last_name: str | None
    estimated_age: int | None
    gender: Optional[str] = None
# ── VISIT SCHEMAS ─────────────────────────────────────────────────────────

class VisitCreate(BaseModel):
    """Data required to start a new hospital encounter session."""
    patient_id: UUID
    entry_type: EntryType
    visit_reason: Optional[str] = Field(default=None, max_length=255)

    model_config = ConfigDict(from_attributes=True)

class VisitRead(ORMBase):
    visit_id: UUID
    patient_id: UUID
    token_number: str
    entry_type: EntryType
    visit_reason: Optional[str]
    stage: VisitStage 
    current_queue_entry_id: Optional[UUID]
    created_at: datetime
    updated_at: Optional[datetime]
    completed_at: Optional[datetime]

class VisitUpdate(BaseModel):
    visit_reason: Optional[str] = Field(default=None, max_length=255)
    model_config = ConfigDict(from_attributes=True)

# ── DEPARTMENT SCHEMAS ────────────────────────────────────────────────────
class DepartmentBase(BaseModel):
    name: str = Field(..., max_length=100, description="The name of the department")
    department_code: str = Field(..., max_length=10, description="Unique short code for the department")
    type: DeptType = DeptType.OPD
    max_capacity: int = 50

# 2. Schema used when CREATING a new Department (This fixes your import error!)
class DepartmentCreate(DepartmentBase):
    pass  # Usually, creation requires the exact same fields as the base

# 3. Schema used when UPDATING an existing Department (All fields optional)
class DepartmentUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    department_code: str | None = Field(None, max_length=10)
    type: DeptType | None = None
    is_active: bool | None = None
    max_capacity: int | None = Field(None, gt=0)


class DepartmentRead(ORMBase):
    dept_id: UUID
    name: str
    department_code: str
    type: DeptType
    is_active: bool
    max_capacity: int = Field(gt=0)



# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

class LoginRequest(BaseModel):
    employee_id: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    staff: StaffRead


# ---------------------------------------------------------
# TOKEN REFRESH
# ---------------------------------------------------------

class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------
# CURRENT USER
# ---------------------------------------------------------

class CurrentUser(BaseModel):
    staff_id: UUID
    employee_id: str
    first_name: str
    last_name: str
    role: StaffRole
    dept_id: UUID


# ---------------------------------------------------------
# PASSWORD CHANGE
# ---------------------------------------------------------

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(
        ..., 
        min_length=8, 
        description="Password must be at least 8 characters long"
    )

    # Optional: Add custom complexity rules (uppercase, digit, special char) if needed
    @field_validator("new_password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in value):
            raise ValueError("Password must contain at least one uppercase letter")
        return value



# ── STAFF / AUTH SCHEMAS ──────────────────────────────────────────────────
class StaffBase(BaseModel):
    employee_id: str
    dept_id: UUID
    first_name: str
    last_name: str
    role: StaffRole
    specialization: Optional[str] = None

class StaffRead(ORMBase):
    staff_id: UUID
    employee_id: str
    first_name: str
    last_name: str
    role: StaffRole

    dept_id: UUID
    department_name: str | None = None
    department_code: str | None = None

    specialization: str | None
    is_on_duty: bool
    is_active: bool



class StaffCreate(StaffBase):
    password: str


class StaffUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    specialization: Optional[str] = None

class StaffDepartmentUpdate(BaseModel):
    dept_id: UUID

class StaffRoleUpdate(BaseModel):
    role: StaffRole

class StaffDutyUpdate(BaseModel):
    is_on_duty: bool

class StaffDutyStatusRead(BaseModel):
    staff_id: UUID
    employee_id: str
    full_name: str
    role: StaffRole
    department_id: UUID
    is_on_duty: bool


class MessageResponse(BaseModel):
    message: str

# ── NEW: DEPARTMENT QUEUE ENTRY SCHEMAS ───────────────────────────────────

class QueueEntryRead(ORMBase):
    """Replaces legacy QueueTokenRead to map cleanly to the current room segments."""
    queue_entry_id: UUID
    visit_id: UUID
    department_id: UUID
    assigned_staff_id: Optional[UUID]
    sequence_number: int
    priority: QueuePriority
    status: QueueEntryStatus
    notes: Optional[str]
    entered_at: datetime
    called_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    # Eager relational embedding parameters
    visit: Optional[VisitRead] = None

class QueueEntryStatusUpdate(BaseModel):
    """Used by staff members to progress tokens (e.g., WAITING -> CALLED)."""
    status: QueueEntryStatus
    notes: Optional[str] = None

class PatientMovementRequest(BaseModel):
    """Payload driving RoutingService.move_patient operations across rooms."""
    target_department_id: UUID
    priority: QueuePriority = QueuePriority.NORMAL
    notes: Optional[str] = None

# ── NEW: SPARENT GEOLOCATION DASHBOARD METRIC SCHEMA ─────────────────────

class LiveLocationRead(BaseModel):
    visit_id: UUID
    token_number: str
    visit_stage: str

    current_queue_entry_id: Optional[UUID] = None

    current_department_id: Optional[UUID] = None
    current_department_name: Optional[str] = None

    status: Optional[str] = None

    assigned_staff_id: Optional[UUID] = None

    position_in_line: int
    estimated_wait_minutes: int

    entered_at: Optional[datetime] = None

# ── VITALS SCHEMAS ────────────────────────────────────────────────────────

class VitalsCreate(BaseModel):
    visit_id: UUID
    temperature: Optional[str] = None
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    oxygen_saturation: Optional[int] = None
    weight: Optional[str] = None

class VitalsRead(ORMBase):
    vital_id: UUID
    visit_id: UUID
    recorded_by: Optional[UUID]
    temperature: Optional[str]
    blood_pressure: Optional[str]
    heart_rate: Optional[int]
    oxygen_saturation: Optional[int]
    weight: Optional[str]
    recorded_at: datetime

# ── AUDIT LOG SCHEMAS ─────────────────────────────────────────────────────

class AuditLogRead(ORMBase):
    log_id: UUID
    entity_id: UUID
    entity_type: str
    action: str
    performed_by: Optional[UUID]
    payload: Dict[str, Any]
    created_at: datetime
#------------------------------------------------------------------------
# Transfer Patient Schemas
#--------------------------------------------------------------------------
class TransferPatientRequest(BaseModel):
    """
    Transfers an active visit to another department.
    Creates the next queue entry and updates the visit.
    """

    visit_id: UUID
    from_department_id: UUID
    to_department_id: UUID

    priority: Optional[QueuePriority] = QueuePriority.NORMAL
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    model_config = ConfigDict(from_attributes=True)

class CompleteDepartmentRequest(BaseModel):
    """
    Marks the current department encounter as complete.
    """

    queue_entry_id: UUID

    notes: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    model_config = ConfigDict(from_attributes=True)


class CompleteDepartmentRequest(BaseModel):
    """
    Marks the current department encounter as complete.
    """

    queue_entry_id: UUID

    notes: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    model_config = ConfigDict(from_attributes=True)


class FinishVisitRequest(BaseModel):
    """
    Closes the entire hospital visit.
    """

    visit_id: UUID

    notes: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    model_config = ConfigDict(from_attributes=True)

class RouteDecision(BaseModel):
    """
    Describes the routing action taken.
    """
    visit_id: UUID
    previous_department_id: UUID | None = None
    current_department_id: UUID | None = None
    queue_entry_id: UUID | None = None
    visit_completed: bool = False
    message: str
    model_config = ConfigDict(from_attributes=True)