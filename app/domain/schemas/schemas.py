"""
Pydantic v2 schemas. Separate Create / Read / Update shapes per entity.
"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator
from app.domain.models.models import StaffRole, TokenStatus, TriageLevel, DeptType


# ── Base config ──────────────────────────────────────────────────────────

class ORMBase(BaseModel):
    model_config = {"from_attributes": True}


# ── Patient ───────────────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    national_id:   str
    first_name:    str
    last_name:     str
    date_of_birth: Optional[date] = None
    blood_type:    Optional[str]  = None
    allergies:     Optional[str]  = None
    phone:         Optional[str]  = None
    email:         Optional[EmailStr] = None

    @field_validator("national_id")
    @classmethod
    def validate_national_id(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 6:
            raise ValueError("national_id must be at least 6 characters")
        return v


class PatientRead(ORMBase):
    patient_id:    UUID
    national_id:   str
    first_name:    str
    last_name:     str
    date_of_birth: Optional[date]
    blood_type:    Optional[str]
    phone:         Optional[str]
    email:         Optional[str]
    created_at:    datetime


class PatientSummary(ORMBase):
    """Lightweight version embedded in token responses."""
    patient_id:  UUID
    national_id: str
    first_name:  str
    last_name:   str
    phone:       Optional[str]


# ── Department ────────────────────────────────────────────────────────────

class DepartmentRead(ORMBase):
    dept_id:      UUID
    name:         str
    code:         str
    type:         DeptType
    is_active:    bool
    max_capacity: int


# ── Staff / Auth ──────────────────────────────────────────────────────────

class StaffRead(ORMBase):
    staff_id:       UUID
    employee_id:    str
    first_name:     str
    last_name:      str
    role:           StaffRole
    specialization: Optional[str]
    is_on_duty:     bool


class LoginRequest(BaseModel):
    employee_id: str
    password:    str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    staff:        StaffRead


# ── Queue ─────────────────────────────────────────────────────────────────

class QueueRead(ORMBase):
    queue_id:   UUID
    dept_id:    UUID
    queue_date: date
    status:     str
    opened_at:  datetime


# ── QueueToken ────────────────────────────────────────────────────────────

class TokenIssueRequest(BaseModel):
    patient_id: UUID
    dept_id:    UUID
    notes:      Optional[str] = None


class QueueTokenRead(ORMBase):
    token_id:     UUID
    token_number: str
    status:       TokenStatus
    triage_level: TriageLevel
    notes:        Optional[str]
    issued_at:    datetime
    called_at:    Optional[datetime]
    completed_at: Optional[datetime]
    patient:      PatientSummary
    queue_id:     UUID


class QueueTokenSummary(ORMBase):
    """Used in the ordered queue list — no nested patient for performance."""
    token_id:     UUID
    token_number: str
    status:       TokenStatus
    triage_level: TriageLevel
    issued_at:    datetime
    patient:      PatientSummary


class TokenStatusUpdate(BaseModel):
    status: TokenStatus
    notes:  Optional[str] = None


# ── Auth dependency payload ───────────────────────────────────────────────

class CurrentUser(BaseModel):
    staff_id:   UUID
    employee_id: str
    role:        StaffRole
    dept_id:     UUID
