from datetime import date, datetime, timezone
from typing import Optional, List, Dict, Any, Union
from uuid import UUID, uuid4
from enum import Enum
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, Field, model_validator
from sqlalchemy import Integer
from app.domain.models.models import (
    StaffRole, DeptType, EntryType, VisitStage,
    QueueEntryStatus, QueuePriority, RegistrationStatus
)


# ════════════════════════════════════════════════════════════════════════════
# SECTION 1: ENUMS & BASE CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

class ORMBase(BaseModel):
    """Base configuration for all ORM-mapped schemas."""
    model_config = ConfigDict(from_attributes=True)


class PatientIdentifierType(str, Enum):
    PHONE = "PHONE"
    NATIONAL_ID = "NATIONAL_ID"


class StationType(str, Enum):
    COUNTER = "COUNTER"
    ROOM = "ROOM"
    WINDOW = "WINDOW"
    DOOR = "DOOR"


class AnnouncementPriority(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class TransferReason(str, Enum):
    DEPARTMENT_TRANSFER = "DEPARTMENT_TRANSFER"
    DIRECT_ROUTING = "DIRECT_ROUTING"
    CLINICAL_REFERRAL = "CLINICAL_REFERRAL"
    RETURN_TO_DEPARTMENT = "RETURN_TO_DEPARTMENT"


class NotificationEventType(str, Enum):
    """Represents a meaningful event within the queue domain."""
    TOKEN_CALLED = "TOKEN_CALLED"
    TOKEN_SERVICE_STARTED = "TOKEN_SERVICE_STARTED"
    TOKEN_COMPLETED = "TOKEN_COMPLETED"
    TOKEN_NO_SHOW = "TOKEN_NO_SHOW"
    PATIENT_ROUTED = "PATIENT_ROUTED"
    QUEUE_UPDATED = "QUEUE_UPDATED"
    ANNOUNCEMENT_CREATED = "ANNOUNCEMENT_CREATED"
    ANNOUNCEMENT_EXPIRED = "ANNOUNCEMENT_EXPIRED"


class NotificationPriority(str, Enum):
    """Urgency level for notification consumers."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationTarget(str, Enum):
    """Identifies consumers interested in notification events."""
    PUBLIC_DISPLAY = "PUBLIC_DISPLAY"
    STAFF_DASHBOARD = "STAFF_DASHBOARD"
    AUDIO_SYSTEM = "AUDIO_SYSTEM"


# ════════════════════════════════════════════════════════════════════════════
# SECTION 2: KIOSK PAYLOADS (No dependencies)
# ════════════════════════════════════════════════════════════════════════════

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
    dept_id: UUID
    department_name: str
    status: QueueEntryStatus


# ════════════════════════════════════════════════════════════════════════════
# SECTION 3: PATIENT SCHEMAS (Standalone)
# ════════════════════════════════════════════════════════════════════════════

class PatientCreate(BaseModel):
    """Used for full registration by staff via Admin/Reception dashboard."""
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
    is_active: bool


class PatientSummary(ORMBase):
    """Lightweight version embedded inside token/queue responses."""
    patient_id: UUID
    national_id: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]


class PatientUpdate(BaseModel):
    """Used by receptionist to complete or edit registration."""
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


class EmergencyPatientRead(BaseModel):
    patient_id: UUID
    temporary_identifier: str
    registration_status: RegistrationStatus
    first_name: str | None
    last_name: str | None
    estimated_age: int | None
    gender: Optional[str] = None


class PatientReconciliation(BaseModel):
    first_name: str
    last_name: str
    national_id: str
    phone: str
    date_of_birth: date
    email: EmailStr | None = None
    blood_type: str | None = None
    allergies: str | None = None


class CompletePatientRegistration(BaseModel):
    """Used by Reception to complete registration for incomplete patients."""
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    national_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
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


class PatientActiveStatusUpdate(BaseModel):
    """Used by authorized staff to activate or deactivate a patient record."""
    is_active: bool


# ════════════════════════════════════════════════════════════════════════════
# SECTION 4: VITALS SCHEMAS (Standalone)
# ════════════════════════════════════════════════════════════════════════════

class VitalsBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    temperature: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    oxygen_saturation: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None


class VitalsCreate(VitalsBase):
    """Payload for POST /visits/{visit_id}/vitals."""
    pass


class VitalsRead(VitalsBase):
    vitals_id: UUID
    visit_id: UUID
    recorded_by: Optional[UUID] = None
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════════════════════
# SECTION 5: DEPARTMENT SCHEMAS (Standalone)
# ════════════════════════════════════════════════════════════════════════════

class DepartmentBase(BaseModel):
    name: str = Field(..., max_length=100, description="The name of the department")
    department_code: str = Field(..., max_length=10, description="Unique short code")
    type: DeptType = DeptType.OPD
    max_capacity: int = 50


class DepartmentCreate(DepartmentBase):
    pass


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


# ════════════════════════════════════════════════════════════════════════════
# SECTION 6: SERVICE POINT SCHEMAS (Defined before Staff and Queue)
# ════════════════════════════════════════════════════════════════════════════

class ServicePointBase(BaseModel):
    code: str
    label: str
    station_type: StationType = StationType.COUNTER
    is_active: bool = True


class ServicePointCreate(ServicePointBase):
    dept_id: UUID


class ServicePointUpdate(BaseModel):
    code: Optional[str] = None
    label: Optional[str] = None
    station_type: Optional[StationType] = None
    is_active: Optional[bool] = None


class ServicePointRead(ServicePointBase):
    service_point_id: UUID
    dept_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ════════════════════════════════════════════════════════════════════════════
# SECTION 7: STAFF SCHEMAS (Before Queue, uses ServicePoint)
# ════════════════════════════════════════════════════════════════════════════

class StaffBase(BaseModel):
    employee_id: str
    dept_id: UUID
    first_name: str
    last_name: str
    role: StaffRole
    specialization: Optional[str] = None


class StaffCreate(StaffBase):
    password: str


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
    active_service_point_id: Optional[UUID] = None


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
    dept_id: UUID
    is_on_duty: bool


# ════════════════════════════════════════════════════════════════════════════
# SECTION 8: AUTH & LOGIN SCHEMAS (Standalone)
# ════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    employee_id: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    staff: StaffRead


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(
        ...,
        min_length=8,
        description="Password must be at least 8 characters long"
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in value):
            raise ValueError("Password must contain at least one uppercase letter")
        return value


class StationBinding(BaseModel):
    """Compact station payload for the top-bar pill / station gate."""
    service_point_id: UUID
    code: str
    label: str
    station_type: StationType
    status: str = "CHECKED_IN"


class CurrentUser(BaseModel):
    staff_id: UUID
    employee_id: str
    first_name: str
    last_name: str
    role: StaffRole
    dept_id: UUID
    station: Optional[StationBinding] = None


# ════════════════════════════════════════════════════════════════════════════
# SECTION 9: VISIT SCHEMAS (Depends on PatientRead and VitalsRead)
# ════════════════════════════════════════════════════════════════════════════

class VisitCreate(BaseModel):
    """Data required to start a new hospital encounter session."""
    patient_id: UUID
    entry_type: EntryType
    visit_reason: Optional[str] = Field(default=None, max_length=255)

    model_config = ConfigDict(from_attributes=True)


class TriageAssessmentUpdate(BaseModel):
    chief_complaint: Optional[str] = None
    triage_assessment: Optional[str] = None


class ClinicalAssessmentUpdate(BaseModel):
    clinical_findings: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None


class ClinicalAssessmentRead(BaseModel):
    visit_id: UUID
    clinical_findings: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VisitRead(BaseModel):
    visit_id: UUID
    patient_id: UUID
    token_number: str
    entry_type: EntryType
    visit_reason: Optional[str] = None
    stage: VisitStage
    chief_complaint: Optional[str] = None
    triage_assessment: Optional[str] = None
    latest_vitals: Optional[VitalsRead] = None
    clinical_findings: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None
    patient: Optional[PatientRead] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VisitUpdate(BaseModel):
    visit_reason: Optional[str] = Field(default=None, max_length=255)
    model_config = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════════════════════
# SECTION 10: QUEUE ENTRY SCHEMAS (Depends on VisitRead and ServicePointRead)
# ════════════════════════════════════════════════════════════════════════════

class QueueEntryRead(ORMBase):
    queue_entry_id: UUID
    visit_id: UUID
    dept_id: UUID
    department_name: Optional[str] = None
    assigned_staff_id: Optional[UUID]
    service_point_id: Optional[UUID] = None
    service_point: Optional[ServicePointRead] = None
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


class QueuePriorityUpdate(BaseModel):
    """Used by authorized staff to update queue priority / acuity."""
    priority: QueuePriority


class PatientMovementRequest(BaseModel):
    """Payload driving RoutingService.move_patient operations across rooms."""
    target_dept_id: UUID
    priority: QueuePriority = QueuePriority.NORMAL
    notes: Optional[str] = None


class TransferPatientRequest(BaseModel):
    """Transfers an active visit to another department."""
    target_dept_id: UUID
    reason: TransferReason = TransferReason.DEPARTMENT_TRANSFER
    priority: Optional[QueuePriority] = None
    notes: Optional[str] = Field(
        default=None,
        description="Mandatory when priority is CRITICAL or when clinical notes required.",
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_transfer(self):
        if self.priority == QueuePriority.CRITICAL and not self.notes:
            raise ValueError("notes are required when priority is CRITICAL")
        return self


class CompleteDepartmentRequest(BaseModel):
    """Marks the current department encounter as complete."""
    queue_entry_id: UUID
    notes: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(from_attributes=True)


class FinishVisitRequest(BaseModel):
    """Closes the entire hospital visit."""
    visit_id: UUID
    notes: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(from_attributes=True)


class RouteDecision(BaseModel):
    """Describes the routing action taken."""
    visit_id: UUID
    previous_dept_id: UUID | None = None
    current_dept_id: UUID | None = None
    queue_entry_id: UUID | None = None
    visit_completed: bool = False
    message: str
    model_config = ConfigDict(from_attributes=True)


# ════════════════════════════════════════════════════════════════════════════
# SECTION 11: LIVE LOCATION & DISPLAY SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class LiveLocationRead(BaseModel):
    visit_id: UUID
    token_number: str
    visit_stage: VisitStage
    current_queue_entry_id: Optional[UUID] = None
    current_dept_id: Optional[UUID] = None
    current_department_name: Optional[str] = None
    status: Optional[QueueEntryStatus] = None
    assigned_staff_id: Optional[UUID] = None
    position_in_line: Optional[int] = None
    estimated_wait_minutes: Optional[int] = None
    entered_at: Optional[datetime] = None


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
    dept_id: UUID
    department_name: str
    active_tokens: list[ActiveTokenDisplay] = Field(
        default_factory=list,
        description="Tokens currently CALLED or IN_PROGRESS",
    )
    next_tokens: list[NextTokenDisplay] = Field(
        default_factory=list,
        description="Upcoming tokens in WAITING status ordered by priority and sequence",
    )
    recent_tokens: list[RecentTokenDisplay] = Field(
        default_factory=list,
        description="Recently serviced or completed tokens",
    )
    waiting_count: int = Field(
        default=0,
        ge=0,
        description="Total number of patients currently waiting",
    )
    estimated_wait_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Estimated wait time in minutes for the next patient",
    )


class DisplayAnnouncement(BaseModel):
    """Broadcast announcement or emergency alert payload."""
    announcement_id: UUID
    priority: AnnouncementPriority
    message: str = Field(min_length=1, max_length=500)
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class DisplaySnapshot(BaseModel):
    """
    Top-level display payload emitted to public digital signage monitors.
    Represents the authoritative current state of the display.
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


# ════════════════════════════════════════════════════════════════════════════
# SECTION 12: NOTIFICATION & EVENT SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class NotificationEvent(BaseModel):
    """
    Presentation-agnostic event describing something within the queue domain.
    Contains enough context for consumers to react without inferring info.
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

    # TOKEN / VISIT CONTEXT
    token_number: str | None = Field(default=None, max_length=20)
    visit_id: UUID | None = Field(default=None)
    queue_entry_id: UUID | None = Field(default=None)

    # DEPARTMENT CONTEXT
    dept_id: UUID | None = Field(default=None)
    department_name: str | None = Field(default=None, max_length=100)
    service_point: str | None = Field(default=None, max_length=100)

    # ROUTING CONTEXT
    source_dept_id: UUID | None = Field(default=None)
    source_department_name: str | None = Field(default=None, max_length=100)
    target_dept_id: UUID | None = Field(default=None)
    target_department_name: str | None = Field(default=None, max_length=100)

    # ANNOUNCEMENT CONTEXT
    announcement_id: UUID | None = Field(default=None)
    announcement_priority: AnnouncementPriority | None = Field(default=None)
    starts_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)

    # MESSAGE
    message: str | None = Field(default=None, max_length=255)

    # CONSUMERS
    targets: list[NotificationTarget] = Field(
        default_factory=list,
        description="Consumers that should react to this event",
    )


# ════════════════════════════════════════════════════════════════════════════
# SECTION 13: SERVICE POINT OCCUPANCY & CHECK-IN
# ════════════════════════════════════════════════════════════════════════════

class ServicePointOccupancy(BaseModel):
    """One row of a department's service point occupancy board."""
    service_point: ServicePointRead
    current_staff: Optional[StaffRead] = None
    active_entry_token: Optional[str] = None
    active_entry_id: Optional[UUID] = None


class StaffCheckInRequest(BaseModel):
    service_point_id: UUID


class CallPatientRequest(BaseModel):
    """Optional body for calling a patient to a specific service point."""
    service_point_id: Optional[UUID] = None


# ════════════════════════════════════════════════════════════════════════════
# SECTION 14: AUDIT & UTILITY SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class AuditLogRead(ORMBase):
    log_id: UUID
    entity_id: UUID
    entity_type: str
    action: str
    performed_by: Optional[UUID]
    payload: Dict[str, Any]
    created_at: datetime


class MessageResponse(BaseModel):
    message: str


# ════════════════════════════════════════════════════════════════════════════
# SECTION 15: MODEL REBUILDS (Resolve forward references)
# ════════════════════════════════════════════════════════════════════════════

# Rebuild VisitRead to ensure VitalsRead forward reference is resolved
VisitRead.model_rebuild()