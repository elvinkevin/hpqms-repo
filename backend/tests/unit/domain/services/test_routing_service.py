"""
Unit tests for RoutingService

Covers:
- Initial kiosk dispatch for all entry types
- Patient transfers between departments
- Live location tracking
- Queue journey history
- Error handling and validation
"""

from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi import HTTPException

from app.domain.models.models import (
    Department,
    DeptType,
    EntryType,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueuePriority,
    RegistrationStatus,
    Visit,
    VisitStage,
)
from app.domain.schemas.schemas import TransferReason
from app.domain.services.routing_service import RoutingService


# ============================================================================
# FIXTURES FOR SERVICE-LEVEL TESTING
# ============================================================================


@pytest.fixture
def mock_visit_service():
    """Mock VisitService"""
    return AsyncMock()


@pytest.fixture
def mock_queue_service():
    """Mock QueueService"""
    return AsyncMock()


@pytest.fixture
def mock_department_service():
    """Mock DepartmentService"""
    return AsyncMock()


@pytest.fixture
def routing_service(db, mock_visit_service, mock_queue_service, mock_department_service):
    """Create RoutingService with mocked dependencies"""
    service = RoutingService(db)
    service.visit_service = mock_visit_service
    service.queue_service = mock_queue_service
    service.department_service = mock_department_service
    return service


# ============================================================================
# HELPER FIXTURES
# ============================================================================


@pytest.fixture
def mock_department():
    """Create a mock active department"""
    dept = MagicMock(spec=Department)
    dept.dept_id = uuid4()
    dept.name = "Triage"
    dept.department_code = "TRIAGE"
    dept.is_active = True
    return dept


@pytest.fixture
def mock_emergency_department():
    """Create a mock emergency department"""
    dept = MagicMock(spec=Department)
    dept.dept_id = uuid4()
    dept.name = "Emergency"
    dept.department_code = "EMERGENCY"
    dept.is_active = True
    return dept


@pytest.fixture
def mock_reception_department():
    """Create a mock reception department"""
    dept = MagicMock(spec=Department)
    dept.dept_id = uuid4()
    dept.name = "Reception"
    dept.department_code = "RECEPTION"
    dept.is_active = True
    return dept


@pytest.fixture
def mock_visit():
    """Create a mock visit"""
    visit = MagicMock(spec=Visit)
    visit.visit_id = uuid4()
    visit.token_number = "W-101"
    visit.entry_type = EntryType.WALK_IN
    visit.stage = VisitStage.ACTIVE
    visit.current_queue_entry_id = None
    visit.patient = MagicMock(spec=Patient)
    visit.patient.registration_status = RegistrationStatus.COMPLETE
    return visit


@pytest.fixture
def mock_queue_entry():
    """Create a mock queue entry"""
    entry = MagicMock(spec=QueueEntry)
    entry.queue_entry_id = uuid4()
    entry.visit_id = uuid4()
    entry.dept_id = uuid4()
    entry.status = QueueEntryStatus.WAITING
    entry.priority = QueuePriority.NORMAL
    entry.entered_at = datetime.utcnow()
    entry.assigned_staff_id = None
    return entry


@pytest.fixture
def mock_in_progress_queue_entry():
    """Create a mock in-progress queue entry"""
    entry = MagicMock(spec=QueueEntry)
    entry.queue_entry_id = uuid4()
    entry.visit_id = uuid4()
    entry.dept_id = uuid4()
    entry.status = QueueEntryStatus.IN_PROGRESS
    entry.priority = QueuePriority.NORMAL
    entry.entered_at = datetime.utcnow()
    entry.assigned_staff_id = uuid4()
    return entry


# ============================================================================
# TEST: INITIAL KIOSK DISPATCH
# ============================================================================


class TestDispatchInitialKioskRoute:
    """Test suite for dispatch_initial_kiosk_route"""

    async def test_dispatch_emergency_patient(
        self,
        routing_service,
        mock_visit,
        mock_emergency_department,
        mock_queue_entry,
    ):
        """Test emergency patients are routed directly to Emergency"""
        mock_visit.entry_type = EntryType.EMERGENCY
        mock_visit.patient.registration_status = RegistrationStatus.COMPLETE

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_code = AsyncMock(
            return_value=mock_emergency_department
        )
        routing_service.transfer_patient = AsyncMock(return_value=mock_queue_entry)

        result = await routing_service.dispatch_initial_kiosk_route(mock_visit.visit_id)

        assert result == mock_queue_entry
        routing_service.transfer_patient.assert_called_once()
        call_kwargs = routing_service.transfer_patient.call_args[1]
        assert call_kwargs["reason"] == TransferReason.DIRECT_ROUTING
        assert call_kwargs["priority"] == QueuePriority.CRITICAL
        assert "Emergency patient" in call_kwargs["notes"]

    async def test_dispatch_incomplete_registration(
        self,
        routing_service,
        mock_visit,
        mock_reception_department,
        mock_queue_entry,
    ):
        """Test incomplete registrations go to Reception"""
        mock_visit.entry_type = EntryType.WALK_IN
        mock_visit.patient.registration_status = RegistrationStatus.INCOMPLETE

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_code = AsyncMock(
            return_value=mock_reception_department
        )
        routing_service.transfer_patient = AsyncMock(return_value=mock_queue_entry)

        result = await routing_service.dispatch_initial_kiosk_route(mock_visit.visit_id)

        assert result == mock_queue_entry
        routing_service.transfer_patient.assert_called_once()
        call_kwargs = routing_service.transfer_patient.call_args[1]
        assert call_kwargs["priority"] == QueuePriority.NORMAL
        assert "registration" in call_kwargs["notes"].lower()

    async def test_dispatch_appointment_patient(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_queue_entry,
    ):
        """Test appointment patients bypass Reception and go to Triage"""
        mock_visit.entry_type = EntryType.APPOINTMENT
        mock_visit.patient.registration_status = RegistrationStatus.COMPLETE

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_code = AsyncMock(
            return_value=mock_department
        )
        routing_service.transfer_patient = AsyncMock(return_value=mock_queue_entry)

        result = await routing_service.dispatch_initial_kiosk_route(mock_visit.visit_id)

        assert result == mock_queue_entry
        routing_service.transfer_patient.assert_called_once()
        call_kwargs = routing_service.transfer_patient.call_args[1]
        assert "Appointment" in call_kwargs["notes"]

    async def test_dispatch_walk_in_patient(
        self,
        routing_service,
        mock_visit,
        mock_reception_department,
        mock_queue_entry,
    ):
        """Test walk-in patients go to Reception"""
        mock_visit.entry_type = EntryType.WALK_IN
        mock_visit.patient.registration_status = RegistrationStatus.COMPLETE

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_code = AsyncMock(
            return_value=mock_reception_department
        )
        routing_service.transfer_patient = AsyncMock(return_value=mock_queue_entry)

        result = await routing_service.dispatch_initial_kiosk_route(mock_visit.visit_id)

        assert result == mock_queue_entry
        routing_service.transfer_patient.assert_called_once()
        call_kwargs = routing_service.transfer_patient.call_args[1]
        assert "Walk-in" in call_kwargs["notes"]

    async def test_dispatch_visit_not_found(self, routing_service):
        """Test 404 when visit doesn't exist"""
        routing_service.visit_service.get_visit = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.dispatch_initial_kiosk_route(uuid4())

        assert exc_info.value.status_code == 404
        assert "Visit not found" in exc_info.value.detail


# ============================================================================
# TEST: TRANSFER PATIENT
# ============================================================================


class TestTransferPatient:
    """Test suite for transfer_patient"""

    async def test_transfer_patient_success(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_in_progress_queue_entry,
        mock_queue_entry,
    ):
        """Test successful patient transfer"""
        staff_id = uuid4()
        mock_in_progress_queue_entry.dept_id = uuid4()  # Different department
        mock_department.dept_id = uuid4()

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=mock_in_progress_queue_entry
        )
        routing_service.queue_service.create_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )
        routing_service.queue_service.get_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )
        routing_service.queue_service.emit_department_event = AsyncMock()

        result = await routing_service.transfer_patient(
            visit_id=mock_visit.visit_id,
            target_dept_id=mock_department.dept_id,
            priority=QueuePriority.NORMAL,
            notes="Patient needs follow-up",
            initiated_by_staff_id=staff_id,
        )

        assert result == mock_queue_entry
        routing_service.queue_service.complete_queue_entry.assert_called_once()
        routing_service.queue_service.create_queue_entry.assert_called_once()
        routing_service.queue_service.emit_department_event.assert_called_once()

    async def test_transfer_inactive_visit(
        self,
        routing_service,
        mock_visit,
        mock_department,
    ):
        """Test transfer fails when visit is not active"""
        mock_visit.stage = VisitStage.COMPLETED

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.transfer_patient(
                visit_id=mock_visit.visit_id,
                target_dept_id=mock_department.dept_id,
            )

        assert exc_info.value.status_code == 409
        assert "no longer active" in exc_info.value.detail

    async def test_transfer_inactive_department(
        self,
        routing_service,
        mock_visit,
        mock_department,
    ):
        """Test transfer fails when target department is inactive"""
        mock_department.is_active = False

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.transfer_patient(
                visit_id=mock_visit.visit_id,
                target_dept_id=mock_department.dept_id,
            )

        assert exc_info.value.status_code == 400
        assert "inactive" in exc_info.value.detail

    async def test_transfer_critical_without_notes(
        self,
        routing_service,
        mock_visit,
        mock_department,
    ):
        """Test transfer fails when CRITICAL priority has no notes"""
        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.transfer_patient(
                visit_id=mock_visit.visit_id,
                target_dept_id=mock_department.dept_id,
                priority=QueuePriority.CRITICAL,
            )

        assert exc_info.value.status_code == 400
        assert "clinical justification" in exc_info.value.detail.lower()

    async def test_transfer_same_department(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_in_progress_queue_entry,
    ):
        """Test transfer fails when trying to transfer to same department"""
        mock_in_progress_queue_entry.dept_id = mock_department.dept_id
        staff_id = uuid4()

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=mock_in_progress_queue_entry
        )

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.transfer_patient(
                visit_id=mock_visit.visit_id,
                target_dept_id=mock_department.dept_id,
                initiated_by_staff_id=staff_id,
            )

        assert exc_info.value.status_code == 409
        assert "already queued" in exc_info.value.detail

    async def test_transfer_not_in_progress(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_queue_entry,
    ):
        """Test transfer fails when queue entry is not IN_PROGRESS"""
        mock_queue_entry.status = QueueEntryStatus.WAITING
        staff_id = uuid4()

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.transfer_patient(
                visit_id=mock_visit.visit_id,
                target_dept_id=mock_department.dept_id,
                initiated_by_staff_id=staff_id,
            )

        assert exc_info.value.status_code == 409
        assert "in-progress" in exc_info.value.detail.lower()

    async def test_transfer_missing_staff_id(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_in_progress_queue_entry,
    ):
        """Test transfer fails when staff_id not provided for active entry"""
        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=mock_in_progress_queue_entry
        )

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.transfer_patient(
                visit_id=mock_visit.visit_id,
                target_dept_id=mock_department.dept_id,
                # No initiated_by_staff_id
            )

        assert exc_info.value.status_code == 400
        assert "staff member" in exc_info.value.detail.lower()

    async def test_transfer_return_visit_escalation(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_queue_entry,
    ):
        """Test return visits are auto-escalated to URGENT"""
        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=None
        )
        routing_service.queue_service.create_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )
        routing_service.queue_service.get_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )
        routing_service.queue_service.emit_department_event = AsyncMock()

        await routing_service.transfer_patient(
            visit_id=mock_visit.visit_id,
            target_dept_id=mock_department.dept_id,
            reason=TransferReason.RETURN_TO_DEPARTMENT,
            priority=QueuePriority.NORMAL,  # Should be escalated to URGENT
        )

        call_kwargs = routing_service.queue_service.create_queue_entry.call_args[1]
        assert call_kwargs["priority"] == QueuePriority.URGENT

    async def test_transfer_no_active_entry(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_queue_entry,
    ):
        """Test transfer with no active queue entry (initial dispatch)"""
        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=None
        )
        routing_service.queue_service.create_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )
        routing_service.queue_service.get_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )
        routing_service.queue_service.emit_department_event = AsyncMock()

        result = await routing_service.transfer_patient(
            visit_id=mock_visit.visit_id,
            target_dept_id=mock_department.dept_id,
        )

        assert result == mock_queue_entry
        # Should not call complete_queue_entry when no active entry
        routing_service.queue_service.complete_queue_entry.assert_not_called()
        routing_service.queue_service.create_queue_entry.assert_called_once()


# ============================================================================
# TEST: GET CURRENT LOCATION
# ============================================================================


class TestGetCurrentLocation:
    """Test suite for get_current_location"""

    async def test_get_current_location_with_active_entry(
        self,
        routing_service,
        mock_visit,
        mock_department,
        mock_queue_entry,
    ):
        """Test retrieving current location with active queue entry"""
        mock_queue_entry.entered_at = datetime.utcnow()

        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )
        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )
        routing_service.queue_service.get_patient_position = AsyncMock(return_value=3)
        routing_service.queue_service.get_estimated_wait_time = AsyncMock(return_value=15)

        result = await routing_service.get_current_location(mock_visit.visit_id)

        assert result["visit_id"] == mock_visit.visit_id
        assert result["token_number"] == mock_visit.token_number
        assert result["current_queue_entry_id"] == mock_queue_entry.queue_entry_id
        assert result["current_dept_id"] == mock_department.dept_id
        assert result["current_department_name"] == mock_department.name
        assert result["position_in_line"] == 3
        assert result["estimated_wait_minutes"] == 15
        assert result["status"] == mock_queue_entry.status.value

    async def test_get_current_location_no_active_entry(
        self,
        routing_service,
        mock_visit,
    ):
        """Test retrieving location when no active queue entry"""
        routing_service.visit_service.get_visit = AsyncMock(return_value=mock_visit)
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=None
        )

        result = await routing_service.get_current_location(mock_visit.visit_id)

        assert result["visit_id"] == mock_visit.visit_id
        assert result["current_queue_entry_id"] is None
        assert result["current_dept_id"] is None
        assert result["current_department_name"] is None
        assert result["status"] is None
        assert result["position_in_line"] == 0
        assert result["estimated_wait_minutes"] == 0

    async def test_get_current_location_invalid_visit(self, routing_service):
        """Test location retrieval for non-existent visit"""
        routing_service.visit_service.get_visit = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Visit not found")
        )

        with pytest.raises(HTTPException):
            await routing_service.get_current_location(uuid4())


# ============================================================================
# TEST: GET TOKEN MOVEMENT HISTORY
# ============================================================================


class TestGetTokenMovementHistory:
    """Test suite for get_token_movement_history"""

    async def test_get_movement_history(
        self,
        routing_service,
        mock_visit,
        mock_queue_entry,
    ):
        """Test retrieving patient movement history"""
        history_entries = [
            MagicMock(spec=QueueEntry, queue_entry_id=uuid4()),
            MagicMock(spec=QueueEntry, queue_entry_id=uuid4()),
            MagicMock(spec=QueueEntry, queue_entry_id=uuid4()),
        ]

        routing_service.visit_service.get_visit = AsyncMock(
            return_value=mock_visit
        )

        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        with patch.object(routing_service, "db") as mock_db:
            # db.execute() is async, but the SQLAlchemy result is not.
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = history_entries

            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await routing_service.get_token_movement_history(
                mock_visit.visit_id
            )

            assert len(result) == 3
            assert result == history_entries
            assert all(isinstance(entry, MagicMock) for entry in result)

            mock_db.execute.assert_awaited_once()

    async def test_get_movement_history_visit_not_found(
        self,
        routing_service,
    ):
        """Test history retrieval for non-existent visit"""

        routing_service.visit_service.get_visit = AsyncMock(
            side_effect=HTTPException(
                status_code=404,
                detail="Visit not found",
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await routing_service.get_token_movement_history(uuid4())

        assert exc_info.value.status_code == 404



# ============================================================================
# TEST: DELEGATED QUEUE OPERATIONS
# ============================================================================


class TestDelegatedQueueOperations:
    """Test suite for delegated queue operations"""

    async def test_call_queue_entry(self, routing_service, mock_queue_entry):
        """Test calling a queue entry"""
        mock_queue_entry.status = QueueEntryStatus.CALLED
        routing_service.queue_service.call_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        result = await routing_service.call_queue_entry(mock_queue_entry.queue_entry_id)

        assert result == mock_queue_entry
        routing_service.queue_service.call_queue_entry.assert_called_once_with(
            mock_queue_entry.queue_entry_id
        )

    async def test_start_queue_entry(self, routing_service, mock_queue_entry):
        """Test starting a queue entry"""
        mock_queue_entry.status = QueueEntryStatus.IN_PROGRESS
        routing_service.queue_service.start_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        result = await routing_service.start_queue_entry(mock_queue_entry.queue_entry_id)

        assert result == mock_queue_entry
        routing_service.queue_service.start_queue_entry.assert_called_once_with(
            mock_queue_entry.queue_entry_id
        )

    async def test_complete_queue_entry(self, routing_service, mock_queue_entry):
        """Test completing a queue entry"""
        mock_queue_entry.status = QueueEntryStatus.COMPLETED
        routing_service.queue_service.complete_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        result = await routing_service.complete_queue_entry(
            mock_queue_entry.queue_entry_id,
            notes="Completed successfully",
        )

        assert result == mock_queue_entry
        routing_service.queue_service.complete_queue_entry.assert_called_once_with(
            mock_queue_entry.queue_entry_id,
            notes="Completed successfully",
        )

    async def test_mark_no_show(self, routing_service, mock_queue_entry):
        """Test marking queue entry as no-show"""
        mock_queue_entry.status = QueueEntryStatus.NO_SHOW
        routing_service.queue_service.mark_no_show = AsyncMock(
            return_value=mock_queue_entry
        )

        result = await routing_service.mark_no_show(
            mock_queue_entry.queue_entry_id,
            notes="Patient didn't show up",
        )

        assert result == mock_queue_entry
        routing_service.queue_service.mark_no_show.assert_called_once_with(
            mock_queue_entry.queue_entry_id,
            notes="Patient didn't show up",
        )

    async def test_cancel_queue_entry(self, routing_service, mock_queue_entry):
        """Test canceling a queue entry"""
        mock_queue_entry.status = QueueEntryStatus.CANCELLED
        routing_service.queue_service.cancel_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        result = await routing_service.cancel_queue_entry(
            mock_queue_entry.queue_entry_id,
            notes="Cancelled by patient",
        )

        assert result == mock_queue_entry
        routing_service.queue_service.cancel_queue_entry.assert_called_once_with(
            mock_queue_entry.queue_entry_id,
            notes="Cancelled by patient",
        )


# ============================================================================
# INTEGRATION-STYLE TESTS
# ============================================================================


class TestRoutingServiceIntegration:
    """Integration tests combining multiple operations"""

    async def test_complete_patient_journey(
        self,
        routing_service,
        mock_visit,
        mock_reception_department,
        mock_department,
        mock_queue_entry,
        mock_in_progress_queue_entry,
    ):
        """Test complete patient journey: dispatch -> transfer -> complete"""

        staff_id = uuid4()

        # ---------------------------------------------------------
        # Step 1: Initial dispatch to Reception
        # ---------------------------------------------------------

        routing_service.visit_service.get_visit = AsyncMock(
            return_value=mock_visit
        )

        routing_service.department_service.get_by_code = AsyncMock(
            return_value=mock_reception_department
        )

        routing_service.department_service.get_by_id = AsyncMock(
            return_value=mock_department
        )

        # IMPORTANT:
        # Initial kiosk dispatch has no existing active queue entry.
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=None
        )

        routing_service.queue_service.create_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        routing_service.queue_service.get_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        routing_service.queue_service.emit_department_event = AsyncMock()

        # Initial dispatch
        dispatch_result = await routing_service.dispatch_initial_kiosk_route(
            mock_visit.visit_id
        )

        assert dispatch_result == mock_queue_entry

        # ---------------------------------------------------------
        # Step 2: Call patient
        # ---------------------------------------------------------

        routing_service.queue_service.call_queue_entry = AsyncMock(
            return_value=mock_queue_entry
        )

        called_result = await routing_service.call_queue_entry(
            mock_queue_entry.queue_entry_id
        )

        assert called_result == mock_queue_entry

        # ---------------------------------------------------------
        # Step 3: Start service
        # ---------------------------------------------------------

        routing_service.queue_service.start_queue_entry = AsyncMock(
            return_value=mock_in_progress_queue_entry
        )

        started_result = await routing_service.start_queue_entry(
            mock_queue_entry.queue_entry_id
        )

        assert started_result == mock_in_progress_queue_entry

        # ---------------------------------------------------------
        # Step 4: Transfer to clinic
        # ---------------------------------------------------------

        # The current queue entry must be IN_PROGRESS.
        mock_in_progress_queue_entry.status = QueueEntryStatus.IN_PROGRESS

        # Make sure current department differs from target department.
        mock_in_progress_queue_entry.dept_id = uuid4()

        # During transfer, the patient now has an active
        # in-progress queue entry.
        routing_service.queue_service.get_active_queue_entry = AsyncMock(
            return_value=mock_in_progress_queue_entry
        )

        new_queue_entry = MagicMock(spec=QueueEntry)
        new_queue_entry.queue_entry_id = uuid4()

        routing_service.queue_service.create_queue_entry = AsyncMock(
            return_value=new_queue_entry
        )

        routing_service.queue_service.get_queue_entry = AsyncMock(
            return_value=new_queue_entry
        )

        routing_service.queue_service.complete_queue_entry = AsyncMock()

        transferred = await routing_service.transfer_patient(
            visit_id=mock_visit.visit_id,
            target_dept_id=mock_department.dept_id,
            initiated_by_staff_id=staff_id,
        )

        assert transferred == new_queue_entry
        routing_service.queue_service.complete_queue_entry.assert_awaited_once()
        routing_service.queue_service.create_queue_entry.assert_awaited()
        routing_service.queue_service.emit_department_event.assert_awaited()


    async def test_discharge_patient_completes_queue_entry_and_visit(
        self,
        db,
        active_visit,
        admin_staff,
    ):
        routing_service = RoutingService(db)
        staff_id = admin_staff.staff_id

        # Put the visit's existing queue entry into IN_PROGRESS so discharge is allowed
        queue_entry = await db.get(QueueEntry, active_visit.current_queue_entry_id)
        queue_entry.assigned_staff_id = staff_id
        queue_entry.status = QueueEntryStatus.IN_PROGRESS
        await db.flush()

        visit_id = queue_entry.visit_id

        # Verify active entry exists before discharge
        current_entry = await routing_service.queue_service.get_active_queue_entry(visit_id)
        assert current_entry is not None

        # Perform discharge via routing service
        await routing_service.discharge_patient(visit_id=visit_id, staff_id=staff_id)

        # Refresh and assert completion status
        await db.refresh(queue_entry)
        assert queue_entry.status == QueueEntryStatus.COMPLETED

        visit = await db.get(Visit, visit_id)
        assert visit.stage == VisitStage.COMPLETED


    async def test_cannot_discharge_waiting_patient(
        self,
        db,
        active_visit,
        admin_staff,
    ):
        # active_visit ships with a WAITING queue entry already attached
        queue_entry = await db.get(QueueEntry, active_visit.current_queue_entry_id)
        queue_entry.status = QueueEntryStatus.WAITING
        await db.flush()

        routing_service = RoutingService(db)

        current_entry = await routing_service.queue_service.get_active_queue_entry(
            active_visit.visit_id
        )

        assert current_entry is not None
        assert current_entry.status == QueueEntryStatus.WAITING

        with pytest.raises(HTTPException) as exc:
            await routing_service.discharge_patient(
                visit_id=active_visit.visit_id,
                staff_id=admin_staff.staff_id,
            )

        assert exc.value.status_code == 409

    async def test_cannot_discharge_called_patient(
        self,
        db,
        active_visit,
        admin_staff,
    ):
        # Use the queue entry that active_visit already has; set status to CALLED
        queue_entry = await db.get(QueueEntry, active_visit.current_queue_entry_id)
        queue_entry.status = QueueEntryStatus.CALLED
        await db.flush()

        routing_service = RoutingService(db)

        with pytest.raises(HTTPException) as exc:
            await routing_service.discharge_patient(
                visit_id=active_visit.visit_id,
                staff_id=admin_staff.staff_id,
            )

        assert exc.value.status_code == 409

    async def test_discharge_unknown_visit_returns_404(
        self,  # <--- Ensure 'self' is the first parameter
        db,
        admin_staff,
    ):
        routing_service = RoutingService(db)

        with pytest.raises(HTTPException) as exc:
            await routing_service.discharge_patient(
                visit_id=uuid.uuid4(),
                staff_id=admin_staff.staff_id,
            )

        assert exc.value.status_code == 404

    async def test_cannot_discharge_completed_visit(
        self,
        db,
        active_visit,
        admin_staff,  # Use existing staff fixture
    ):
        staff_id = admin_staff.staff_id

        # Use the visit's existing queue entry, assign real staff_id, set IN_PROGRESS
        queue_entry = await db.get(QueueEntry, active_visit.current_queue_entry_id)
        queue_entry.assigned_staff_id = staff_id
        queue_entry.status = QueueEntryStatus.IN_PROGRESS
        await db.flush()

        routing_service = RoutingService(db)

        # First discharge succeeds
        await routing_service.discharge_patient(
            visit_id=active_visit.visit_id,
            staff_id=staff_id,
        )

        # Attempting to discharge an already completed visit fails (HTTP 409)
        with pytest.raises(HTTPException) as exc:
            await routing_service.discharge_patient(
                visit_id=active_visit.visit_id,
                staff_id=staff_id,
            )

        assert exc.value.status_code == 409

    async def test_discharge_does_not_create_new_queue_entry(
        self,
        db,
        active_visit,
        admin_staff,
    ):
        staff_id = admin_staff.staff_id

        # Use the visit's existing queue entry, assign real staff_id, set IN_PROGRESS
        queue_entry = await db.get(QueueEntry, active_visit.current_queue_entry_id)
        queue_entry.assigned_staff_id = staff_id
        queue_entry.status = QueueEntryStatus.IN_PROGRESS
        await db.flush()

        routing_service = RoutingService(db)

        await routing_service.discharge_patient(
            visit_id=active_visit.visit_id,
            staff_id=staff_id,
        )

        remaining_active = (
            await routing_service.queue_service.get_active_queue_entry(
                active_visit.visit_id
            )
        )

        assert remaining_active is None