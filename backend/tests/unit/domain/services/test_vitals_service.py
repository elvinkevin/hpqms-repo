"""
Unit tests for VitalsService.

Tests the service layer business logic in isolation, using mock/real
database sessions but without going through the HTTP layer.
"""
import pytest
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException, status

from app.domain.models.models import (
    Visit,
    Vitals,
    VisitStage,
    EntryType,
)
from app.domain.schemas.schemas import VitalsCreate, TriageAssessmentUpdate
from app.domain.services.vitals_service import VitalsService


pytestmark = pytest.mark.asyncio


# ==============================================================================
# 1. RECORD VITALS TESTS
# ==============================================================================

class TestRecordVitals:
    """Test vitals recording functionality."""

    async def test_record_vitals_success(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Successfully record vitals for an active visit."""
        vitals_in = VitalsCreate(
            temperature=98.6,
            systolic_bp=120,
            diastolic_bp=80,
            heart_rate=72,
            respiratory_rate=16,
            oxygen_saturation=98,
            weight=70.5,
            height=175.0,
        )

        vitals = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=vitals_in,
        )

        assert vitals.visit_id == active_visit.visit_id
        assert vitals.recorded_by == doctor_staff.staff_id
        assert vitals.temperature == 98.6
        assert vitals.heart_rate == 72
        assert vitals.recorded_at is not None
        assert isinstance(vitals.recorded_at, datetime)

    async def test_record_vitals_minimal_fields(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Record vitals with only required fields."""
        vitals_in = VitalsCreate(
            temperature=37.0,
        )

        vitals = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=vitals_in,
        )

        assert vitals.temperature == 37.0
        assert vitals.heart_rate is None  # Optional field
        assert vitals.systolic_bp is None

    async def test_record_vitals_unknown_visit(
        self,
        db,
        doctor_staff,
    ):
        """Recording vitals for non-existent visit raises 404."""
        vitals_in = VitalsCreate(temperature=98.6)

        with pytest.raises(HTTPException) as exc:
            await VitalsService.record_vitals(
                db=db,
                visit_id=uuid4(),  # Non-existent visit
                staff_id=doctor_staff.staff_id,
                vitals_in=vitals_in,
            )

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Visit" in exc.value.detail
        assert "not found" in exc.value.detail

    async def test_record_vitals_preserves_existing(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Recording new vitals doesn't delete previous records."""
        # Record first vitals
        vitals_in_1 = VitalsCreate(temperature=98.0, heart_rate=70)
        vitals_1 = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=vitals_in_1,
        )

        # Record second vitals
        vitals_in_2 = VitalsCreate(temperature=98.6, heart_rate=72)
        vitals_2 = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=vitals_in_2,
        )

        # Both should exist
        assert vitals_1.vitals_id != vitals_2.vitals_id
        assert vitals_1.temperature == 98.0
        assert vitals_2.temperature == 98.6

    async def test_record_vitals_multiple_visits(
        self,
        db,
        existing_patient,
        doctor_staff,
    ):
        """Record vitals for different visits independently."""
        # Create two visits
        visit_1 = Visit(
            patient_id=existing_patient.patient_id,
            token_number="W-101",
            entry_type=EntryType.WALK_IN,
            stage=VisitStage.ACTIVE,
        )
        visit_2 = Visit(
            patient_id=existing_patient.patient_id,
            token_number="W-102",
            entry_type=EntryType.WALK_IN,
            stage=VisitStage.ACTIVE,
        )
        db.add(visit_1)
        db.add(visit_2)
        await db.flush()

        # Record vitals for each
        vitals_1 = await VitalsService.record_vitals(
            db=db,
            visit_id=visit_1.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(temperature=98.0),
        )

        vitals_2 = await VitalsService.record_vitals(
            db=db,
            visit_id=visit_2.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(temperature=98.6),
        )

        assert vitals_1.visit_id == visit_1.visit_id
        assert vitals_2.visit_id == visit_2.visit_id
        assert vitals_1.temperature != vitals_2.temperature


# ==============================================================================
# 2. GET VITALS TESTS
# ==============================================================================

class TestGetVitals:
    """Test vitals retrieval functionality."""

    async def test_get_latest_vitals_success(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Get the most recent vitals for a visit."""
        # Record multiple vitals
        vitals_1 = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(temperature=98.0, heart_rate=70),
        )

        vitals_2 = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(temperature=98.6, heart_rate=72),
        )

        # Get latest
        latest = await VitalsService.get_latest_vitals(
            db=db,
            visit_id=active_visit.visit_id,
        )

        # Should be the second one (most recent)
        assert latest.vitals_id == vitals_2.vitals_id
        assert latest.temperature == 98.6
        assert latest.heart_rate == 72

    async def test_get_latest_vitals_no_records(
        self,
        db,
        active_visit,
    ):
        """Get latest vitals returns None when no records exist."""
        latest = await VitalsService.get_latest_vitals(
            db=db,
            visit_id=active_visit.visit_id,
        )

        assert latest is None

    async def test_get_latest_vitals_unknown_visit(
        self,
        db,
    ):
        """Get latest vitals for non-existent visit returns None."""
        latest = await VitalsService.get_latest_vitals(
            db=db,
            visit_id=uuid4(),
        )

        assert latest is None

    async def test_get_all_vitals_success(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Get all vitals for a visit in reverse chronological order."""
        # Record vitals
        vitals_1 = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(temperature=98.0),
        )

        vitals_2 = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(temperature=98.6),
        )

        vitals_3 = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(temperature=99.0),
        )

        # Get all
        all_vitals = await VitalsService.get_all_vitals(
            db=db,
            visit_id=active_visit.visit_id,
        )

        # Should be in reverse chronological order (newest first)
        assert len(all_vitals) == 3
        assert all_vitals[0].vitals_id == vitals_3.vitals_id
        assert all_vitals[1].vitals_id == vitals_2.vitals_id
        assert all_vitals[2].vitals_id == vitals_1.vitals_id

    async def test_get_all_vitals_empty(
        self,
        db,
        active_visit,
    ):
        """Get all vitals returns empty sequence when no records exist."""
        all_vitals = await VitalsService.get_all_vitals(
            db=db,
            visit_id=active_visit.visit_id,
        )

        assert len(all_vitals) == 0

    async def test_get_all_vitals_unknown_visit(
        self,
        db,
    ):
        """Get all vitals for non-existent visit returns empty sequence."""
        all_vitals = await VitalsService.get_all_vitals(
            db=db,
            visit_id=uuid4(),
        )

        assert len(all_vitals) == 0


# ==============================================================================
# 3. UPDATE TRIAGE ASSESSMENT TESTS
# ==============================================================================

class TestUpdateTriageAssessment:
    """Test triage assessment update functionality."""

    async def test_update_triage_assessment_success(
        self,
        db,
        active_visit,
    ):
        """Successfully update chief complaint and triage assessment."""
        assessment = TriageAssessmentUpdate(
            chief_complaint="Severe headache",
            triage_assessment="Urgent - patient reports migraines",
        )

        updated_visit = await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=assessment,
        )

        assert updated_visit.visit_id == active_visit.visit_id
        assert updated_visit.chief_complaint == "Severe headache"
        assert updated_visit.triage_assessment == "Urgent - patient reports migraines"

    async def test_update_triage_assessment_partial(
        self,
        db,
        active_visit,
    ):
        """Update only some triage fields (exclude_unset behavior)."""
        # Initial update
        assessment_1 = TriageAssessmentUpdate(
            chief_complaint="Headache",
            triage_assessment="Monitor",
        )
        await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=assessment_1,
        )

        # Partial update - only chief complaint
        assessment_2 = TriageAssessmentUpdate(
            chief_complaint="Severe headache",
        )
        updated_visit = await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=assessment_2,
        )

        assert updated_visit.chief_complaint == "Severe headache"
        assert updated_visit.triage_assessment == "Monitor"  # Unchanged

    async def test_update_triage_assessment_unknown_visit(
        self,
        db,
    ):
        """Updating triage for non-existent visit raises 404."""
        assessment = TriageAssessmentUpdate(
            chief_complaint="Headache",
        )

        with pytest.raises(HTTPException) as exc:
            await VitalsService.update_triage_assessment(
                db=db,
                visit_id=uuid4(),
                assessment_in=assessment,
            )

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_triage_assessment_idempotent(
        self,
        db,
        active_visit,
    ):
        """Multiple updates with same data don't cause issues."""
        assessment = TriageAssessmentUpdate(
            chief_complaint="Chest pain",
        )

        visit_1 = await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=assessment,
        )

        visit_2 = await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=assessment,
        )

        assert visit_1.chief_complaint == visit_2.chief_complaint

    async def test_update_triage_preserves_other_visit_fields(
        self,
        db,
        active_visit,
    ):
        """Updating triage doesn't affect other visit fields."""
        # Record initial state
        original_stage = active_visit.stage
        original_token = active_visit.token_number

        # Update triage
        assessment = TriageAssessmentUpdate(
            chief_complaint="Test complaint",
        )
        updated_visit = await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=assessment,
        )

        # Other fields should be unchanged
        assert updated_visit.stage == original_stage
        assert updated_visit.token_number == original_token


# ==============================================================================
# 4. EDGE CASES & INTEGRATION TESTS
# ==============================================================================

class TestVitalsIntegration:
    """Test combined vitals and triage workflows."""

    async def test_vitals_and_assessment_workflow(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Complete workflow: record vitals and update assessment."""
        # Step 1: Record vitals
        vitals = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(
                temperature=98.6,
                heart_rate=72,
                systolic_bp=120,
                diastolic_bp=80,
            ),
        )

        # Step 2: Update assessment
        visit = await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=TriageAssessmentUpdate(
                chief_complaint="Routine checkup",
                triage_assessment="Normal vitals, no concerns",
            ),
        )

        # Verify both were recorded
        latest_vitals = await VitalsService.get_latest_vitals(
            db=db,
            visit_id=active_visit.visit_id,
        )

        assert latest_vitals.vitals_id == vitals.vitals_id
        assert visit.chief_complaint == "Routine checkup"

    async def test_multiple_vitals_same_visit(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Record multiple vitals progressions for a single visit."""
        vitals_records = []

        # Simulate monitoring over time with changing vitals
        for i, temp in enumerate([37.0, 37.5, 38.0, 37.8], 1):
            vitals = await VitalsService.record_vitals(
                db=db,
                visit_id=active_visit.visit_id,
                staff_id=doctor_staff.staff_id,
                vitals_in=VitalsCreate(
                    temperature=temp,
                    heart_rate=70 + i * 2,
                ),
            )
            vitals_records.append(vitals)

        # Verify history
        all_vitals = await VitalsService.get_all_vitals(
            db=db,
            visit_id=active_visit.visit_id,
        )

        assert len(all_vitals) == 4
        # Temperature trend: 37.0 → 37.5 → 38.0 → 37.8
        assert all_vitals[3].temperature == 37.0  # First (oldest)
        assert all_vitals[0].temperature == 37.8  # Last (newest)

    async def test_critical_vitals_assessment_correlation(
        self,
        db,
        active_visit,
        doctor_staff,
    ):
        """Record abnormal vitals and update assessment accordingly."""
        # Record critical vitals
        vitals = await VitalsService.record_vitals(
            db=db,
            visit_id=active_visit.visit_id,
            staff_id=doctor_staff.staff_id,
            vitals_in=VitalsCreate(
                temperature=40.5,  # High fever
                heart_rate=120,    # Tachycardia
                oxygen_saturation=88,  # Low O2
            ),
        )

        # Update assessment to reflect critical status
        visit = await VitalsService.update_triage_assessment(
            db=db,
            visit_id=active_visit.visit_id,
            assessment_in=TriageAssessmentUpdate(
                chief_complaint="Severe fever and shortness of breath",
                triage_assessment="High fever, tachycardia, low O2 sat. Admit to monitoring.",
            ),
        )

        assert vitals.temperature == 40.5
