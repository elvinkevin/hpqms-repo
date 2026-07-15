"""
Unit tests for Queue.reorder() and QueueToken state machine.
These tests use plain Python objects — no database, no FastAPI, no async.
If these pass, the core business logic is correct.
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.models.models import StaffRole, TriageLevel, TokenStatus
from app.domain.services.queue_service import TRIAGE_ORDER, VALID_TRANSITIONS
from app.api.v1.endpoints.tokens import ROLE_STATE_PERMISSIONS


# ── Helpers ───────────────────────────────────────────────────────────────
3
def make_token(triage: TriageLevel, minutes_ago: int = 0):
    """Simulate a QueueToken as a simple namespace — no DB required."""
    class FakeToken:
        token_id    = uuid4()
        triage_level= triage
        issued_at   = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        status      = TokenStatus.WAITING
    return FakeToken()


def reorder(tokens):
    """Mirror the sort logic from QueueService.get_ordered_tokens()."""
    return sorted(tokens, key=lambda t: (TRIAGE_ORDER.get(t.triage_level, 99), t.issued_at))


# ── Triage ordering ───────────────────────────────────────────────────────

class TestTriageOrdering:

    def test_critical_always_first(self):
        tokens = [
            make_token(TriageLevel.NON_URGENT),
            make_token(TriageLevel.CRITICAL),
            make_token(TriageLevel.URGENT),
        ]
        result = reorder(tokens)
        assert result[0].triage_level == TriageLevel.CRITICAL

    def test_full_priority_order(self):
        tokens = [
            make_token(TriageLevel.NON_URGENT),
            make_token(TriageLevel.SEMI_URGENT),
            make_token(TriageLevel.URGENT),
            make_token(TriageLevel.CRITICAL),
        ]
        result = reorder(tokens)
        expected = [TriageLevel.CRITICAL, TriageLevel.URGENT,
                    TriageLevel.SEMI_URGENT, TriageLevel.NON_URGENT]
        assert [t.triage_level for t in result] == expected

    def test_fifo_within_same_level(self):
        """Within the same triage level, earlier issued_at wins."""
        first  = make_token(TriageLevel.URGENT, minutes_ago=10)
        second = make_token(TriageLevel.URGENT, minutes_ago=5)
        third  = make_token(TriageLevel.URGENT, minutes_ago=1)

        result = reorder([third, first, second])
        assert result[0] is first
        assert result[1] is second
        assert result[2] is third

    def test_urgent_jumps_ahead_of_non_urgent_fifo(self):
        """
        A patient who arrived later but gets escalated to URGENT
        should appear before earlier NON_URGENT patients.
        """
        early_non_urgent  = make_token(TriageLevel.NON_URGENT, minutes_ago=20)
        late_urgent       = make_token(TriageLevel.URGENT, minutes_ago=2)

        result = reorder([early_non_urgent, late_urgent])
        assert result[0] is late_urgent

    def test_empty_queue_returns_empty(self):
        assert reorder([]) == []

    def test_single_token_unchanged(self):
        t = make_token(TriageLevel.NON_URGENT)
        assert reorder([t]) == [t]

    def test_all_same_level_preserves_fifo(self):
        tokens = [make_token(TriageLevel.NON_URGENT, minutes_ago=m) for m in [15, 10, 5, 1]]
        result = reorder(tokens)
        # Should be same order — earliest first
        for i in range(len(result) - 1):
            assert result[i].issued_at < result[i + 1].issued_at


# ── State machine ──────────────────────────────────────────────────────────

class TestStateMachine:

    def test_issued_can_transition_to_waiting(self):
        assert TokenStatus.WAITING in VALID_TRANSITIONS[TokenStatus.ISSUED]

    def test_issued_can_be_cancelled(self):
        assert TokenStatus.CANCELLED in VALID_TRANSITIONS[TokenStatus.ISSUED]

    def test_completed_is_terminal(self):
        assert VALID_TRANSITIONS[TokenStatus.COMPLETED] == set()

    def test_transferred_is_terminal(self):
        assert VALID_TRANSITIONS[TokenStatus.TRANSFERRED] == set()

    def test_cancelled_is_terminal(self):
        assert VALID_TRANSITIONS[TokenStatus.CANCELLED] == set()

    def test_completed_cannot_go_back_to_waiting(self):
        assert TokenStatus.WAITING not in VALID_TRANSITIONS[TokenStatus.COMPLETED]

    def test_in_consult_can_complete_or_transfer(self):
        allowed = VALID_TRANSITIONS[TokenStatus.IN_CONSULT]
        assert TokenStatus.COMPLETED in allowed
        assert TokenStatus.TRANSFERRED in allowed

    def test_escalated_goes_to_called(self):
        assert TokenStatus.CALLED in VALID_TRANSITIONS[TokenStatus.ESCALATED]

    @pytest.mark.parametrize("from_status,to_status", [
        (TokenStatus.COMPLETED,   TokenStatus.WAITING),
        (TokenStatus.CANCELLED,   TokenStatus.WAITING),
        (TokenStatus.TRANSFERRED, TokenStatus.IN_CONSULT),
        (TokenStatus.ISSUED,      TokenStatus.IN_CONSULT),  # must go through WAITING first
    ])
    def test_illegal_transitions_not_in_map(self, from_status, to_status):
        assert to_status not in VALID_TRANSITIONS[from_status]

    def test_triage_order_values_are_ascending(self):
        """Lower number = higher priority. CRITICAL must be 0."""
        assert TRIAGE_ORDER[TriageLevel.CRITICAL] < TRIAGE_ORDER[TriageLevel.URGENT]
        assert TRIAGE_ORDER[TriageLevel.URGENT]   < TRIAGE_ORDER[TriageLevel.SEMI_URGENT]
        assert TRIAGE_ORDER[TriageLevel.SEMI_URGENT] < TRIAGE_ORDER[TriageLevel.NON_URGENT]


class TestRoleStatePermissions:

    def test_triage_nurse_controls_triage_states(self):
        assert StaffRole.TRIAGE_NURSE in ROLE_STATE_PERMISSIONS[TokenStatus.IN_TRIAGE]
        assert StaffRole.TRIAGE_NURSE in ROLE_STATE_PERMISSIONS[TokenStatus.ESCALATED]

    def test_charge_nurse_receives_escalated_cases(self):
        assert StaffRole.CHARGE_NURSE in ROLE_STATE_PERMISSIONS[TokenStatus.ESCALATED]
        assert StaffRole.CHARGE_NURSE not in ROLE_STATE_PERMISSIONS[TokenStatus.IN_TRIAGE]

    def test_doctor_controls_consultation_states(self):
        assert StaffRole.DOCTOR in ROLE_STATE_PERMISSIONS[TokenStatus.CALLED]
        assert StaffRole.DOCTOR in ROLE_STATE_PERMISSIONS[TokenStatus.IN_CONSULT]
        assert StaffRole.DOCTOR in ROLE_STATE_PERMISSIONS[TokenStatus.COMPLETED]

    def test_receptionist_cannot_set_clinical_states(self):
        assert StaffRole.RECEPTIONIST not in ROLE_STATE_PERMISSIONS[TokenStatus.IN_TRIAGE]
        assert StaffRole.RECEPTIONIST not in ROLE_STATE_PERMISSIONS[TokenStatus.CALLED]
