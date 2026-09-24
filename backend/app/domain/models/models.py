from datetime import datetime
import uuid
from enum import Enum as PyEnum
from sqlalchemy import Column, String, Date, DateTime, Text, ForeignKey, Enum, Integer, Index, UniqueConstraint, Boolean, Float, text, true, false
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base

# ── 1. ENUMS & STRUCTS ───────────────────────────────────────────────────

class EntryType(str, PyEnum):
    WALK_IN = "WALK_IN"
    APPOINTMENT = "APPOINTMENT"
    EMERGENCY = "EMERGENCY"
    REFERRAL = "REFERRAL"

class VisitStage(str, PyEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class QueueEntryStatus(str, PyEnum):
    WAITING = "WAITING"
    CALLED = "CALLED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"

class QueuePriority(str, PyEnum):
    NORMAL = "NORMAL"
    SEMI_URGENT = "SEMI_URGENT"
    URGENT = "URGENT"
    CRITICAL = "CRITICAL"

class RegistrationStatus(str, PyEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"

class DeptType(str, PyEnum):
    OPD = "OPD"
    EMERGENCY = "EMERGENCY"
    SPECIALIST = "SPECIALIST"
    PAEDS = "PAEDS"

class StaffRole(str, PyEnum):
    RECEPTIONIST = "RECEPTIONIST"
    NURSE = "NURSE"
    TRIAGE_NURSE = "TRIAGE_NURSE"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"

class AppointmentStatus(str, PyEnum):
    SCHEDULED = "SCHEDULED"
    CHECKED_IN = "CHECKED_IN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"

class NotificationStatus(str, PyEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"

class NotificationChannel(str, PyEnum):
    SMS = "SMS"
    DISPLAY = "DISPLAY"
    PA = "PA"

class ArrivalMode(str, PyEnum):

    WALK_IN = "WALK_IN"

    AMBULANCE = "AMBULANCE"

    POLICE = "POLICE"

    TRANSFER = "TRANSFER"

    AIR_AMBULANCE = "AIR_AMBULANCE"

class StationType(str, PyEnum):
    COUNTER = "COUNTER"
    ROOM = "ROOM"
    WINDOW = "WINDOW"
    DOOR = "DOOR"

# ── 2. IDENTITY PATIENT MODEL ───────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (Index("idx_patient_name", "first_name", "last_name"),)

    patient_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Workflow & Identity Management
    registration_status = Column(
        Enum(RegistrationStatus),
        nullable=False,
        server_default=RegistrationStatus.INCOMPLETE.value,
    )
    temporary_identifier = Column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        comment="System-generated ID for John Doe / Emergency intake (e.g., TEMP-20260728-992)",
    )
    national_id = Column(String(20), unique=True, nullable=True, index=True)

    # Demographics
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    date_of_birth = Column(Date, nullable=True)
    estimated_age = Column(
        Integer,
        nullable=True,
        comment="Used during emergency intake when exact DOB is unknown",
    )
    gender = Column(String(20))
    email = Column(String(255))

    # Medical Info
    blood_type = Column(String(10))
    allergies = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default="true")

    # Audit & Identity Reconciliation Tracking
    reconciled_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when temporary identity was reconciled to official details",
    )
    reconciled_by = Column(
        UUID(as_uuid=True),
        ForeignKey("staff.staff_id"),
        nullable=True,
        comment="User ID of staff member who performed identity reconciliation",
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Domain Helper Properties
    @property
    def is_temporary(self) -> bool:
        """Convenience check for unreconciled/emergency records."""
        return self.registration_status == RegistrationStatus.INCOMPLETE

    # Relationships
    visits = relationship("Visit", back_populates="patient")
    appointments = relationship("Appointment", back_populates="patient")

    # FIXED: Use the Python Class Name "Staff" (or explicit Patient.reconciled_by)
    reconciler = relationship(
        "Staff", foreign_keys="[Patient.reconciled_by]", backref="reconciled_patients"
    )


# ── 3. VISITS & QUEUES WORKFLOW ENGINES ──────────────────────────────────

class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (Index("idx_visit_token", "token_number"),)

    visit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.patient_id"), nullable=False, index=True)
    token_number = Column(String(20), unique=True, nullable=False)
    entry_type = Column(Enum(EntryType), nullable=False)
    visit_reason = Column(String(255), nullable=True)

    # ── T1 Additions ───────────────────────────────────────────────────────
    chief_complaint = Column(String(500), nullable=True)
    triage_assessment = Column(Text, nullable=True)
    # ───────────────────────────────────────────────────────────────────────

    @property
    def latest_vitals(self):
        """Returns the most recent Vitals entry from the loaded vitals collection."""
        if hasattr(self, "vitals") and self.vitals:
            sorted_vitals = sorted(
                self.vitals,
                key=lambda v: v.recorded_at if v.recorded_at else datetime.min,
                reverse=True,
            )
            return sorted_vitals[0]
        return None


    stage = Column(Enum(VisitStage), nullable=False, server_default=VisitStage.ACTIVE.value, index=True)

    # D3.1 Clinical Assessment Fields
    clinical_findings = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    treatment_plan = Column(Text, nullable=True)

    # Database-level fix for DDL & Alembic migrations
    current_queue_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "queue_entries.queue_entry_id",
            use_alter=True,
            name="fk_visits_current_queue_entry_id"
        ),
        nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    patient = relationship("Patient", back_populates="visits")

    # ORM-level fix for insert/update ordering in application logic
    current_queue_entry = relationship(
        "QueueEntry",
        foreign_keys=[current_queue_entry_id],
        post_update=True
    )
    queue_entries = relationship(
        "QueueEntry",
        back_populates="visit",
        foreign_keys="QueueEntry.visit_id",
        order_by="QueueEntry.entered_at"
    )

    # ── T3 Relationship ───────────────────────────────────────────────────
    # lazy="selectin" so vitals are eagerly loaded; the latest_vitals
    # property is read during response serialization (outside the async
    # session's greenlet context) and must never trigger a lazy load.
    vitals = relationship(
        "Vitals",
        back_populates="visit",
        order_by="Vitals.recorded_at",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # ───────────────────────────────────────────────────────────────────────

class QueueEntry(Base):
    __tablename__ = "queue_entries"
    __table_args__ = (
        Index(
            "idx_department_waiting",
            "dept_id",
            "status",
            "priority",
            "sequence_number",
        ),
        Index("idx_visit_queue", "visit_id"),
        Index("idx_department_sequence", "dept_id", "sequence_number"),
        Index("idx_queue_entered_at", "entered_at"),
        Index("idx_queue_service_point", "service_point_id"),
        Index(
            "uq_active_entry_per_visit",
            "visit_id",
            unique=True,
            postgresql_where=text("status IN ('WAITING','CALLED','IN_PROGRESS')"),
        ),
        Index(
            "uq_active_entry_per_staff",
            "assigned_staff_id",
            unique=True,
            postgresql_where=text(
                "assigned_staff_id IS NOT NULL "
                "AND status IN ('CALLED','IN_PROGRESS')"
            ),
        ),
        Index(
            "uq_active_entry_per_service_point",
            "service_point_id",
            unique=True,
            postgresql_where=text(
                "service_point_id IS NOT NULL "
                "AND status IN ('CALLED','IN_PROGRESS')"
            ),
        ),
    )

    queue_entry_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.visit_id"), nullable=False)
    dept_id = Column(UUID(as_uuid=True), ForeignKey("departments.dept_id"), nullable=False)
    assigned_staff_id = Column(UUID(as_uuid=True), ForeignKey("staff.staff_id"), nullable=True)
    service_point_id = Column(UUID(as_uuid=True), ForeignKey("service_points.service_point_id"), nullable=True)
    sequence_number = Column(Integer, nullable=False)
    priority = Column(Enum(QueuePriority), nullable=False, server_default=QueuePriority.NORMAL.value)
    status = Column(Enum(QueueEntryStatus), nullable=False, server_default=QueueEntryStatus.WAITING.value)
    notes = Column(Text)

    entered_at = Column(DateTime(timezone=True), server_default=func.now())
    called_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    no_show_at = Column(DateTime(timezone=True), nullable=True)

    visit = relationship("Visit", back_populates="queue_entries", foreign_keys=[visit_id])
    department = relationship("Department", back_populates="queue_entries")
    assigned_staff = relationship("Staff", back_populates="queue_entries")
    service_point = relationship(
        "ServicePoint",
        back_populates="queue_entries",
        lazy="selectin",  # eager load: accessed during response serialization
    )


class DepartmentQueueCounter(Base):
    __tablename__ = "department_queue_counters"
    __table_args__ = (
        UniqueConstraint("dept_id", "queue_date", name="uq_dept_queue_date"),
        Index("idx_department_queue_date", "dept_id", "queue_date"),
    )

    counter_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dept_id = Column(UUID(as_uuid=True), ForeignKey("departments.dept_id"), nullable=False, index=True)
    queue_date = Column(Date, nullable=False, index=True)
    last_sequence = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DailyTokenCounter(Base):
    __tablename__ = "daily_token_counters"
    __table_args__ = (UniqueConstraint("counter_date", "entry_type", name="uq_date_entry_type"),)

    counter_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    counter_date = Column(Date, nullable=False, index=True)
    entry_type = Column(Enum(EntryType), nullable=False, index=True)
    last_number = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── 4. CONSOLIDATED DEPARTMENT, STAFF & AUXILIARY MODELS ─────────────────

class Department(Base):
    __tablename__ = "departments"

    dept_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    department_code = Column(String(10), unique=True, nullable=False, index=True)
    type = Column(Enum(DeptType), nullable=False, server_default=DeptType.OPD.value)
    is_active = Column(Boolean, nullable=False, server_default=true())
    max_capacity = Column(Integer, nullable=False, server_default="50")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    staff = relationship("Staff", back_populates="department", foreign_keys="[Staff.dept_id]")
    queue_entries = relationship("QueueEntry", back_populates="department")
    service_points = relationship("ServicePoint", back_populates="department", cascade="all, delete-orphan")


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (
        Index("idx_staff_role", "role"),
        Index("idx_staff_department", "dept_id"),
        Index("idx_staff_active_sp", "active_service_point_id"),
    )

    staff_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(String(20), unique=True, nullable=False, index=True)
    dept_id = Column(UUID(as_uuid=True), ForeignKey("departments.dept_id"), nullable=False)
    active_service_point_id = Column(UUID(as_uuid=True), ForeignKey("service_points.service_point_id"), nullable=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(Enum(StaffRole), nullable=False)
    specialization = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=true())
    is_on_duty = Column(Boolean, nullable=False, server_default=false())
    admin_setup_complete = Column(Boolean, nullable=False, server_default=true())
    requires_password_change = Column(Boolean, nullable=False, server_default=false())
    password_reset_code_hash = Column(String(255), nullable=True)
    password_reset_code_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    department = relationship("Department", back_populates="staff", foreign_keys=[dept_id])
    active_service_point = relationship("ServicePoint", back_populates="active_staff", foreign_keys=[active_service_point_id])
    queue_entries = relationship("QueueEntry", back_populates="assigned_staff")
    appointments = relationship("Appointment", back_populates="assigned_staff")



class ServicePoint(Base):
    __tablename__ = "service_points"
    __table_args__ = (
        Index("idx_service_point_dept", "dept_id"),
        Index("uq_dept_code", "dept_id", "code", unique=True),
    )

    service_point_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dept_id = Column(UUID(as_uuid=True), ForeignKey("departments.dept_id"), nullable=False)
    code = Column(String(20), nullable=False)  # e.g., "RC-01"
    label = Column(String(100), nullable=False)  # e.g., "Reception Desk 1"
    station_type = Column(Enum(StationType), nullable=False, server_default=StationType.COUNTER.value)
    is_active = Column(Boolean, nullable=False, server_default=true())

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    department = relationship("Department", back_populates="service_points")
    queue_entries = relationship("QueueEntry", back_populates="service_point")
    active_staff = relationship("Staff", back_populates="active_service_point", foreign_keys="[Staff.active_service_point_id]")

class Vitals(Base):
    __tablename__ = "vitals"

    vitals_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    visit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("visits.visit_id"),
        nullable=False,
        index=True,
    )
    recorded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("staff.staff_id"),
        nullable=True,
    )

    temperature = Column(Float, nullable=True)                   # °C / °F
    systolic_bp = Column(Integer, nullable=True)                 # mmHg
    diastolic_bp = Column(Integer, nullable=True)                # mmHg
    heart_rate = Column(Integer, nullable=True)                  # bpm
    respiratory_rate = Column(Integer, nullable=True)            # breaths/min
    oxygen_saturation = Column(Integer, nullable=True)           # %
    weight = Column(Float, nullable=True)                        # kg / lbs
    height = Column(Float, nullable=True)                        # cm / in

    recorded_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    visit = relationship("Visit", back_populates="vitals")
    recorder = relationship("Staff")


# ── 5. MISSING APPOINTMENTS DEFINITION ───────────────────────────────────

class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("idx_appointment_date", "appointment_date"),
        Index("idx_appointment_status", "status"),
    )

    appointment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.patient_id"), nullable=False)
    assigned_staff_id = Column(UUID(as_uuid=True), ForeignKey("staff.staff_id"), nullable=True, index=True)
    appointment_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(AppointmentStatus), nullable=False, server_default=AppointmentStatus.SCHEDULED.value)
    reason = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    patient = relationship("Patient", back_populates="appointments")
    assigned_staff = relationship("Staff", back_populates="appointments")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notification_status", "status"),
        Index("idx_notification_channel", "channel"),
    )

    notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visit_id = Column(UUID(as_uuid=True), ForeignKey("visits.visit_id"), nullable=False, index=True)
    queue_entry_id = Column(UUID(as_uuid=True), ForeignKey("queue_entries.queue_entry_id"), nullable=True)
    channel = Column(Enum(NotificationChannel), nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False, server_default=NotificationStatus.PENDING.value)
    message = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_performed_by", "performed_by"),
        Index("idx_audit_action", "action"),
    )

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    performed_by = Column(UUID(as_uuid=True), ForeignKey("staff.staff_id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSONB)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def log_id(self) -> uuid.UUID:
        """Alias for AuditLogRead schema compatibility."""
        return self.audit_id
