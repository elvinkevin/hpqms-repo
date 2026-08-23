from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, Field
from sqlalchemy import Integer
from app.domain.models.models import (
    StaffRole, DeptType, EntryType, VisitStage, 
    QueueEntryStatus, QueuePriority, RegistrationStatus
)
from enum import Enum
from uuid import UUID, uuid4
# ── Base Configuration Mixin ──────────────────────────────────────────────

class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# ── KIOSK TOUCHSCREEN PAYLOADS ────────────────────────────────────────────

class PatientIdentifierType(str, Enum):
    PHONE = "PHONE"
    NATIONAL_ID = "NATIONAL_ID"

class KioskCheckInRequest(BaseModel):
    identifier: str = Field(min_length=1)
    identifier_type: PatientIdentifierType
    visit_type: EntryType


class KioskCheckInResponse(BaseModel):
    patient_id: UUID
    visit_id: UUID
    queue_entry_id: UUID

    token_number: str
    entry_type: EntryType

    department_id: UUID
    department_name: str

    status: QueueEntryStatus


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




class CompletePatientRegistration(BaseModel):
    """
    Used by Reception to complete registration for an existing
    incomplete patient, such as a kiosk patient.
    """

    # Required administrative identity
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str

    # Identity / contact
    national_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    # Clinical information is optional and does not determine
    # registration completeness.
    blood_type: Optional[str] = None
    allergies: Optional[str] = None

    @model_validator(mode="after")
    def validate_contact_info(self):
        if not self.phone and not self.email:
            raise ValueError(
                "At least one contact method (phone or email) "
                "is required to complete registration."
            )

        return self
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

    patient: Optional[PatientRead] = None

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
    queue_entry_id: UUID
    visit_id: UUID
    department_id: UUID
    department_name: Optional[str] = None

    assigned_staff_id: Optional[UUID]
    sequence_number: int
    priority: QueuePriority
    status: QueueEntryStatus
    notes: Optional[str]

    entered_at: datetime
    called_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

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
    visit_stage: VisitStage

    current_queue_entry_id: Optional[UUID] = None

    current_department_id: Optional[UUID] = None
    current_department_name: Optional[str] = None

    status: Optional[QueueEntryStatus] = None

    assigned_staff_id: Optional[UUID] = None

    position_in_line: Optional[int] = None
    estimated_wait_minutes: Optional[int] = None

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


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class AnnouncementPriority(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY STATE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ActiveTokenDisplay(BaseModel):
    """Token currently being processed or called at a service point."""

    token_number: str
    service_point: str | None = None
    status: QueueEntryStatus
    called_at: datetime | None = None


class NextTokenDisplay(BaseModel):
    """Token scheduled next in line within the department queue."""

    token_number: str


class RecentTokenDisplay(BaseModel):
    """Token recently processed or completed in the department."""

    token_number: str


class DepartmentDisplay(BaseModel):
    """Aggregated display view for a single department queue state."""

    department_id: UUID
    department_name: str

    active_tokens: list[ActiveTokenDisplay] = Field(
        default_factory=list,
        description="Tokens currently CALLED or IN_PROGRESS",
    )

    next_tokens: list[NextTokenDisplay] = Field(
        default_factory=list,
        description=(
            "Upcoming tokens in WAITING status ordered by "
            "priority and sequence"
        ),
    )

    recent_tokens: list[RecentTokenDisplay] = Field(
        default_factory=list,
        description="Recently serviced or completed tokens",
    )

    waiting_count: int = Field(
        default=0,
        ge=0,
        description="Total number of patients currently waiting in this department",
    )

    estimated_wait_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Estimated wait time in minutes for the next patient in line",
    )


class DisplayAnnouncement(BaseModel):
    """Broadcast announcement or emergency alert payload."""

    announcement_id: UUID

    priority: AnnouncementPriority

    message: str = Field(
        min_length=1,
        max_length=500,
    )

    starts_at: datetime | None = None

    expires_at: datetime | None = None


class DisplaySnapshot(BaseModel):
    """
    Top-level display payload emitted to public digital signage monitors.

    This represents the authoritative current state of the display.
    """

    facility_name: str | None = None

    server_timestamp: datetime

    departments: list[DepartmentDisplay] = Field(
        default_factory=list,
        description="Current queue state for monitored departments",
    )

    announcements: list[DisplayAnnouncement] = Field(
        default_factory=list,
        description="Currently active facility announcements",
    )


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION EVENT ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class NotificationEventType(str, Enum):
    """
    Represents a meaningful event that occurred within the
    queue or notification domain.
    """

    TOKEN_CALLED = "TOKEN_CALLED"
    TOKEN_SERVICE_STARTED = "TOKEN_SERVICE_STARTED"
    TOKEN_COMPLETED = "TOKEN_COMPLETED"
    TOKEN_NO_SHOW = "TOKEN_NO_SHOW"

    PATIENT_ROUTED = "PATIENT_ROUTED"

    QUEUE_UPDATED = "QUEUE_UPDATED"

    ANNOUNCEMENT_CREATED = "ANNOUNCEMENT_CREATED"
    ANNOUNCEMENT_EXPIRED = "ANNOUNCEMENT_EXPIRED"


class NotificationPriority(str, Enum):
    """
    Determines how urgently a consumer should react to an event.
    """

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationTarget(str, Enum):
    """
    Identifies consumers interested in a notification event.
    """

    PUBLIC_DISPLAY = "PUBLIC_DISPLAY"
    STAFF_DASHBOARD = "STAFF_DASHBOARD"
    AUDIO_SYSTEM = "AUDIO_SYSTEM"


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION EVENT
# ─────────────────────────────────────────────────────────────────────────────

class NotificationEvent(BaseModel):
    """
    Presentation-agnostic event describing something that happened
    within the HPQMS queue or notification domain.

    The event contains enough contextual information for consumers
    to react without having to infer missing information.
    """

    event_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this notification event",
    )

    event_type: NotificationEventType

    priority: NotificationPriority = Field(
        default=NotificationPriority.NORMAL,
        description="Urgency with which consumers should react",
    )

    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the event occurred",
    )

    # ─────────────────────────────────────────────────────────────────────
    # TOKEN / VISIT CONTEXT
    # ─────────────────────────────────────────────────────────────────────

    token_number: str | None = Field(
        default=None,
        max_length=20,
        description="Public queue token associated with the event",
    )

    visit_id: UUID | None = Field(
        default=None,
        description="Visit associated with the event",
    )

    queue_entry_id: UUID | None = Field(
        default=None,
        description="Queue entry associated with the event",
    )

    # ─────────────────────────────────────────────────────────────────────
    # GENERAL DEPARTMENT CONTEXT
    # ─────────────────────────────────────────────────────────────────────

    department_id: UUID | None = Field(
        default=None,
        description=(
            "Primary department associated with the event. "
            "Used for events involving a single department."
        ),
    )

    department_name: str | None = Field(
        default=None,
        max_length=100,
        description="Display name of the primary department",
    )

    service_point: str | None = Field(
        default=None,
        max_length=100,
        description="Service point associated with the event",
    )

    # ─────────────────────────────────────────────────────────────────────
    # ROUTING CONTEXT
    # ─────────────────────────────────────────────────────────────────────

    source_department_id: UUID | None = Field(
        default=None,
        description=(
            "Department from which the patient/token is being routed."
        ),
    )

    source_department_name: str | None = Field(
        default=None,
        max_length=100,
        description="Display name of the source department",
    )

    target_department_id: UUID | None = Field(
        default=None,
        description=(
            "Department to which the patient/token is being routed."
        ),
    )

    target_department_name: str | None = Field(
        default=None,
        max_length=100,
        description="Display name of the target department",
    )

    # ─────────────────────────────────────────────────────────────────────
    # ANNOUNCEMENT CONTEXT
    # ─────────────────────────────────────────────────────────────────────

    announcement_id: UUID | None = Field(
        default=None,
        description="Announcement associated with the event",
    )

    announcement_priority: AnnouncementPriority | None = Field(
        default=None,
        description="Priority of the announcement",
    )

    starts_at: datetime | None = Field(
        default=None,
        description="Time at which the announcement becomes active",
    )

    expires_at: datetime | None = Field(
        default=None,
        description="Time at which the announcement expires",
    )

    # ─────────────────────────────────────────────────────────────────────
    # HUMAN-READABLE MESSAGE
    # ─────────────────────────────────────────────────────────────────────

    message: str | None = Field(
        default=None,
        max_length=255,
        description="Optional human-readable event or announcement message",
    )

    # ─────────────────────────────────────────────────────────────────────
    # EVENT CONSUMERS
    # ─────────────────────────────────────────────────────────────────────

    targets: list[NotificationTarget] = Field(
        default_factory=list,
        description="Consumers that should react to this event",
    )



class TransferReason(str, Enum):
    DEPARTMENT_TRANSFER = "DEPARTMENT_TRANSFER"
    DIRECT_ROUTING = "DIRECT_ROUTING"
    CLINICAL_REFERRAL = "CLINICAL_REFERRAL"
    RETURN_TO_DEPARTMENT = "RETURN_TO_DEPARTMENT"


from pydantic import BaseModel, Field, model_validator


class TransferPatientRequest(BaseModel):
    target_department_id: UUID

    reason: TransferReason = TransferReason.DEPARTMENT_TRANSFER

    priority: QueuePriority = QueuePriority.NORMAL

    notes: Optional[str] = Field(
        default=None,
        description="Mandatory when priority is CRITICAL or when clinical notes are required.",
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_transfer(self):
        if self.priority == QueuePriority.CRITICAL and not self.notes:
            raise ValueError(
                "notes are required when priority is CRITICAL"
            )

        return self
