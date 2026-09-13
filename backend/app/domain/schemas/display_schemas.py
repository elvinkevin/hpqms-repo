from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field

from app.domain.models.models import QueueEntryStatus
from typing import Optional

class AnnouncementPriority(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class ActiveTokenDisplay(BaseModel):
    """Token currently being processed or called at a service point."""
    token_number: str
    service_point_id: Optional[UUID] = None
    service_point: Optional[str] = None  # e.g., "Reception Desk 1" or "Room 03"
    status: QueueEntryStatus
    called_at: Optional[datetime] = None
    assigned_staff_id: Optional[UUID] = None


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
        description="Tokens currently CALLED or IN_PROGRESS"
    )

    next_tokens: list[NextTokenDisplay] = Field(
        default_factory=list,
        description="Upcoming tokens in WAITING status ordered by priority and sequence"
    )

    recent_tokens: list[RecentTokenDisplay] = Field(
        default_factory=list,
        description="Recently serviced or completed tokens"
    )

    waiting_count: int = Field(
        default=0,
        ge=0,
        description="Total number of patients currently waiting in this department"
    )

    estimated_wait_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Estimated wait time in minutes for the next patient in line"
    )


class DisplayAnnouncement(BaseModel):
    """Broadcast announcement or emergency alert payload."""
    announcement_id: UUID
    priority: AnnouncementPriority
    message: str
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class DisplaySnapshot(BaseModel):
    """Top-level display payload emitted to public digital signage monitors."""
    facility_name: str | None = None
    server_timestamp: datetime

    departments: list[DepartmentDisplay] = Field(
        default_factory=list,
        description="List of department queue states monitored by this display"
    )

    announcements: list[DisplayAnnouncement] = Field(
        default_factory=list,
        description="Active facility announcements or ticker messages"
    )