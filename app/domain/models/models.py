"""
ORM models — one file for Phase 1. Split into per-entity files in later phases.
Every table uses UUID primary keys. Enums are defined here so Alembic can detect them.
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, DateTime,
    ForeignKey, Enum, func, Date,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base


# ── Enums ─────────────────────────────────────────────────────────────────

class StaffRole(str, PyEnum):
    RECEPTIONIST = "RECEPTIONIST"
    NURSE        = "NURSE"
    TRIAGE_NURSE = "TRIAGE_NURSE"
    DOCTOR       = "DOCTOR"
    CHARGE_NURSE = "CHARGE_NURSE"
    ADMIN        = "ADMIN"


class TokenStatus(str, PyEnum):
    ISSUED      = "ISSUED"
    WAITING     = "WAITING"
    IN_TRIAGE   = "IN_TRIAGE"
    ESCALATED   = "ESCALATED"
    CALLED      = "CALLED"
    IN_CONSULT  = "IN_CONSULT"
    COMPLETED   = "COMPLETED"
    TRANSFERRED = "TRANSFERRED"
    CANCELLED   = "CANCELLED"


class TriageLevel(str, PyEnum):
    NON_URGENT  = "NON_URGENT"
    SEMI_URGENT = "SEMI_URGENT"
    URGENT      = "URGENT"
    CRITICAL    = "CRITICAL"


class DeptType(str, PyEnum):
    OPD        = "OPD"
    EMERGENCY  = "EMERGENCY"
    SPECIALIST = "SPECIALIST"
    PAEDS      = "PAEDS"


# ── Models ────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    patient_id   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    national_id  = Column(String(20), unique=True, nullable=False, index=True)
    first_name   = Column(String(100), nullable=False)
    last_name    = Column(String(100), nullable=False)
    date_of_birth= Column(Date, nullable=True)
    blood_type   = Column(String(20), nullable=True)
    allergies    = Column(Text, nullable=True)
    phone        = Column(String(20), nullable=True)
    email        = Column(String(255), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    tokens       = relationship("QueueToken", back_populates="patient")
    appointments = relationship("Appointment", back_populates="patient")


class Department(Base):
    __tablename__ = "departments"

    dept_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name         = Column(String(100), nullable=False)
    code         = Column(String(10), unique=True, nullable=False)  # e.g. "OPD", "CARD"
    type         = Column(Enum(DeptType), nullable=False, default=DeptType.OPD)
    is_active    = Column(Boolean, default=True)
    max_capacity = Column(Integer, default=50)

    staff        = relationship("Staff", back_populates="department")
    queues       = relationship("Queue", back_populates="department")


class Staff(Base):
    __tablename__ = "staff"

    staff_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id   = Column(String(20), unique=True, nullable=False)
    dept_id       = Column(UUID(as_uuid=True), ForeignKey("departments.dept_id"), nullable=False)
    first_name    = Column(String(100), nullable=False)
    last_name     = Column(String(100), nullable=False)
    role          = Column(Enum(StaffRole), nullable=False)
    specialization= Column(String(100), nullable=True)   # doctors only
    hashed_password=Column(String(255), nullable=False)
    is_on_duty    = Column(Boolean, default=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    department    = relationship("Department", back_populates="staff")
    assigned_tokens = relationship("QueueToken", back_populates="assigned_doctor",
                                   foreign_keys="QueueToken.assigned_doctor_id")


class Queue(Base): 
    __tablename__ = "queues"

    queue_id     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dept_id      = Column(UUID(as_uuid=True), ForeignKey("departments.dept_id"), nullable=False)
    queue_date   = Column(Date, nullable=False, default=func.current_date())
    status       = Column(String(20), default="OPEN")
    opened_at    = Column(DateTime(timezone=True), server_default=func.now())
    closed_at    = Column(DateTime(timezone=True), nullable=True)

    department   = relationship("Department", back_populates="queues")
    tokens       = relationship("QueueToken", back_populates="queue",
                                order_by="QueueToken.issued_at")


class QueueToken(Base):
    __tablename__ = "queue_tokens"

    token_id     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_number = Column(String(20), nullable=False)           # e.g. OPD-004
    queue_id     = Column(UUID(as_uuid=True), ForeignKey("queues.queue_id"), nullable=False)
    patient_id   = Column(UUID(as_uuid=True), ForeignKey("patients.patient_id"), nullable=False)
    assigned_doctor_id = Column(UUID(as_uuid=True), ForeignKey("staff.staff_id"), nullable=True)

    status       = Column(Enum(TokenStatus), nullable=False, default=TokenStatus.ISSUED)
    triage_level = Column(Enum(TriageLevel), nullable=False, default=TriageLevel.NON_URGENT)
    notes        = Column(Text, nullable=True)

    issued_at    = Column(DateTime(timezone=True), server_default=func.now())
    called_at    = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    queue           = relationship("Queue", back_populates="tokens")
    patient         = relationship("Patient", back_populates="tokens")
    assigned_doctor = relationship("Staff", back_populates="assigned_tokens",
                                   foreign_keys=[assigned_doctor_id])
    vitals          = relationship("Vitals", back_populates="token", uselist=False)
    notifications   = relationship("Notification", back_populates="token")


class Vitals(Base):
    __tablename__ = "vitals"

    vital_id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id          = Column(UUID(as_uuid=True), ForeignKey("queue_tokens.token_id"), nullable=False)
    recorded_by       = Column(UUID(as_uuid=True), ForeignKey("staff.staff_id"), nullable=True)
    temperature       = Column(String(10), nullable=True)   # degrees Celsius
    blood_pressure    = Column(String(15), nullable=True)   # "systolic/diastolic"
    heart_rate        = Column(Integer, nullable=True)
    oxygen_saturation = Column(Integer, nullable=True)      # SpO2 %
    weight            = Column(String(10), nullable=True)   # kg
    recorded_at       = Column(DateTime(timezone=True), server_default=func.now())

    token             = relationship("QueueToken", back_populates="vitals")


class Appointment(Base):
    __tablename__ = "appointments"

    appt_id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id   = Column(UUID(as_uuid=True), ForeignKey("patients.patient_id"), nullable=False)
    doctor_id    = Column(UUID(as_uuid=True), ForeignKey("staff.staff_id"), nullable=True)
    dept_id      = Column(UUID(as_uuid=True), ForeignKey("departments.dept_id"), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    status       = Column(String(20), default="SCHEDULED")
    reason       = Column(Text, nullable=True)
    converted_token_id = Column(UUID(as_uuid=True), ForeignKey("queue_tokens.token_id"), nullable=True)

    patient      = relationship("Patient", back_populates="appointments")


class Notification(Base):
    __tablename__ = "notifications"

    notif_id    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id    = Column(UUID(as_uuid=True), ForeignKey("queue_tokens.token_id"), nullable=True)
    patient_id  = Column(UUID(as_uuid=True), ForeignKey("patients.patient_id"), nullable=True)
    channel     = Column(String(20), nullable=False)   # SMS, DASHBOARD, PA, DISPLAY
    message     = Column(Text, nullable=False)
    status      = Column(String(20), default="PENDING")
    sent_at     = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, default=0)

    token       = relationship("QueueToken", back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id    = Column(UUID(as_uuid=True), nullable=False)
    entity_type  = Column(String(50), nullable=False)  # "QueueToken", "Patient", etc.
    action       = Column(String(100), nullable=False)
    performed_by = Column(UUID(as_uuid=True), ForeignKey("staff.staff_id"), nullable=True)
    payload      = Column(JSONB, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
